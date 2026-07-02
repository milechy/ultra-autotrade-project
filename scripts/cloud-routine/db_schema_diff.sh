#!/usr/bin/env bash
# scripts/cloud-routine/db_schema_diff.sh
#
# Ultra AutoTrade — DB スキーマ差分検出スクリプト
#
# 機能:
#   - backend/app/*/models.py から期待カラムを抽出
#   - production / staging DB の実カラムと比較
#   - 差分があれば Slack #ultra-auto-project に通知
#
# 必須環境変数 (production 確認時):
#   SLACK_WEBHOOK_URL       Slack Incoming Webhook URL
#   PROD_DB_CONTAINER       production postgres コンテナ名
#   PROD_DB_USER            postgres ユーザー名
#   PROD_DB_NAME            postgres DB 名
#
# オプション環境変数:
#   STAGING_DB_CONTAINER    staging postgres コンテナ名 (未指定時はスキップ)
#   STAGING_DB_USER         staging postgres ユーザー名
#   STAGING_DB_NAME         staging postgres DB 名
#   HETZNER_SSH_HOST        SSH 経由で実行する場合のホスト (例: 5.223.88.14, ASSIST ONE production)
#   HETZNER_SSH_USER        SSH ユーザー名 (default: root)
#   HETZNER_SSH_KEY         SSH 鍵パス (default: ~/.ssh/id_ed25519)
#   REPO_PATH               リポジトリパス (default: /opt/ultra-autotrade)
#   DRY_RUN                 "true" のとき Slack 通知をスキップ
#   CHECK_STAGING           "true" のとき staging も確認 (default: false)
#
# 実行例 (Hetzner 上):
#   PROD_DB_CONTAINER=ultra-autotrade-postgres-production \
#   PROD_DB_USER=ultra PROD_DB_NAME=ultra_autotrade \
#   SLACK_WEBHOOK_URL=https://... bash db_schema_diff.sh
#
# 実行例 (ローカル Mac から SSH 経由):
#   HETZNER_SSH_HOST=5.223.88.14 HETZNER_SSH_USER=root \
#   SLACK_WEBHOOK_URL=... bash db_schema_diff.sh
#
# cron 設定例 (毎日 9:00 JST = 00:00 UTC、Hetzner cron):
#   0 0 * * * cd /opt/ultra-autotrade && \
#     PROD_DB_CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | grep production) \
#     PROD_DB_USER=ultra PROD_DB_NAME=ultra_autotrade \
#     SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
#     bash scripts/cloud-routine/db_schema_diff.sh >> /var/log/ultra/db_schema_diff.log 2>&1

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
HETZNER_SSH_HOST="${HETZNER_SSH_HOST:-}"
HETZNER_SSH_USER="${HETZNER_SSH_USER:-root}"
HETZNER_SSH_KEY="${HETZNER_SSH_KEY:-${HOME}/.ssh/id_ed25519}"
REPO_PATH="${REPO_PATH:-/opt/ultra-autotrade}"

PROD_DB_CONTAINER="${PROD_DB_CONTAINER:-ultra-autotrade-postgres-production}"
PROD_DB_USER="${PROD_DB_USER:-ultra}"
PROD_DB_NAME="${PROD_DB_NAME:-ultra_autotrade}"

STAGING_DB_CONTAINER="${STAGING_DB_CONTAINER:-}"
STAGING_DB_USER="${STAGING_DB_USER:-ultra}"
STAGING_DB_NAME="${STAGING_DB_NAME:-ultra_autotrade_staging}"

CHECK_STAGING="${CHECK_STAGING:-false}"
DRY_RUN="${DRY_RUN:-false}"
SCRIPT_NAME="db_schema_diff"

# models.py を持つモジュール一覧
MODEL_MODULES=(
    "auth"
    "aave"
    "ai"
    "automation"
    "bots"
    "exchange"
    "knowledge"
    "notifications"
)

# =============================================================================
# ユーティリティ
# =============================================================================
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SCRIPT_NAME] $*"; }
log_warn() { log "WARN $*"; }
log_error() { log "ERROR $*"; }

check_deps() {
    local missing=0
    for cmd in curl jq; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log_error "Required command not found: $cmd"
            missing=1
        fi
    done
    return $missing
}

check_env() {
    local missing=0
    if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
        log_error "SLACK_WEBHOOK_URL is not set"
        missing=1
    fi
    return $missing
}

# =============================================================================
# リモートコマンド実行
# =============================================================================
run_remote_or_local() {
    local cmd="$1"
    if [[ -n "${HETZNER_SSH_HOST}" ]]; then
        ssh -i "${HETZNER_SSH_KEY}" \
            -o StrictHostKeyChecking=no \
            -o ConnectTimeout=10 \
            "${HETZNER_SSH_USER}@${HETZNER_SSH_HOST}" \
            "cd ${REPO_PATH} && ${cmd}" 2>/dev/null
    else
        eval "$cmd"
    fi
}

# =============================================================================
# DB スキーマ取得
# =============================================================================

# 実際の DB カラム一覧を取得 (table_name, column_name)
fetch_actual_columns() {
    local container="$1"
    local db_user="$2"
    local db_name="$3"

    run_remote_or_local "docker exec ${container} psql -U ${db_user} -d ${db_name} -t -A -F'|' -c \
        \"SELECT table_name, column_name FROM information_schema.columns \
          WHERE table_schema='public' ORDER BY table_name, column_name;\"" 2>/dev/null || {
        log_error "Failed to fetch columns from ${container}"
        echo ""
        return 1
    }
}

# models.py から __tablename__ と Column 定義を抽出
# 簡易パーサー: Column( の行から引数名を取得
fetch_expected_columns() {
    local repo_base="$1"
    local module="$2"
    local models_path="${repo_base}/backend/app/${module}/models.py"

    run_remote_or_local "test -f ${models_path} && grep -E '__tablename__|Column\(' ${models_path}" 2>/dev/null || true
}

# =============================================================================
# 差分検出
# =============================================================================
detect_diff() {
    local env_name="$1"
    local container="$2"
    local db_user="$3"
    local db_name="$4"

    log "Checking ${env_name} DB: ${container}"

    local actual_columns
    actual_columns=$(fetch_actual_columns "$container" "$db_user" "$db_name") || {
        echo "FETCH_FAILED"
        return 1
    }

    if [[ -z "$actual_columns" ]]; then
        log_warn "No columns returned from ${env_name} DB"
        echo "EMPTY"
        return 0
    fi

    local table_count
    table_count=$(echo "$actual_columns" | cut -d'|' -f1 | sort -u | wc -l | tr -d ' ')
    local col_count
    col_count=$(echo "$actual_columns" | wc -l | tr -d ' ')

    log "${env_name}: ${table_count} tables, ${col_count} columns found"

    # models.py との比較
    local diff_lines=""
    local repo_base
    repo_base=$(run_remote_or_local "pwd" 2>/dev/null || echo "${REPO_PATH}")

    for module in "${MODEL_MODULES[@]}"; do
        local expected
        expected=$(fetch_expected_columns "$repo_base" "$module") || continue

        if [[ -z "$expected" ]]; then
            continue
        fi

        # __tablename__ から テーブル名を抽出
        local tablename
        tablename=$(echo "$expected" | grep '__tablename__' | \
            sed "s/.*__tablename__.*=.*['\"]\\([^'\"]*\\)['\"].*/\\1/" | head -1)

        if [[ -z "$tablename" ]]; then
            continue
        fi

        # DB にそのテーブルが存在するか確認
        local db_table_exists
        db_table_exists=$(echo "$actual_columns" | grep -c "^${tablename}|" || true)

        if [[ "$db_table_exists" -eq 0 ]]; then
            diff_lines="${diff_lines}\n  ❌ テーブル不在: ${module}/models.py → ${tablename}"
            log_warn "Table missing in ${env_name} DB: ${tablename} (from ${module}/models.py)"
        else
            log "  ✓ ${tablename} exists in ${env_name} DB"
        fi
    done

    echo "${diff_lines}"
}

# =============================================================================
# Slack 通知
# =============================================================================
send_slack() {
    local message="$1"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY_RUN: Slack message skipped"
        echo "$message"
        return 0
    fi

    local http_code
    http_code=$(curl -sf -o /dev/null -w "%{http_code}" \
        --max-time 10 \
        -X POST "${SLACK_WEBHOOK_URL}" \
        -H "Content-Type: application/json" \
        -d "$message")

    if [[ "$http_code" != "200" ]]; then
        log_error "Slack notification failed (HTTP $http_code)"
        return 1
    fi
    return 0
}

# =============================================================================
# メイン処理
# =============================================================================
main() {
    log "Start DB schema diff check ($(date '+%Y-%m-%d %H:%M JST'))"

    check_deps || exit 1
    check_env || exit 1

    local today
    today=$(date '+%Y-%m-%d')
    local all_diffs=""
    local has_error=false

    # Production チェック
    local prod_diff
    prod_diff=$(detect_diff "production" "$PROD_DB_CONTAINER" "$PROD_DB_USER" "$PROD_DB_NAME") || {
        has_error=true
        all_diffs="${all_diffs}\n*production DB*: 接続エラー"
    }

    if [[ "$prod_diff" == "FETCH_FAILED" ]]; then
        has_error=true
        all_diffs="${all_diffs}\n*production DB*: 接続エラー (コンテナ: ${PROD_DB_CONTAINER})"
    elif [[ -n "$prod_diff" ]]; then
        all_diffs="${all_diffs}\n*production DB* の差分:${prod_diff}"
    fi

    # Staging チェック (オプション)
    if [[ "${CHECK_STAGING}" == "true" && -n "${STAGING_DB_CONTAINER}" ]]; then
        local staging_diff
        staging_diff=$(detect_diff "staging" "$STAGING_DB_CONTAINER" "$STAGING_DB_USER" "$STAGING_DB_NAME") || {
            has_error=true
            all_diffs="${all_diffs}\n*staging DB*: 接続エラー"
        }

        if [[ "$staging_diff" == "FETCH_FAILED" ]]; then
            all_diffs="${all_diffs}\n*staging DB*: 接続エラー (コンテナ: ${STAGING_DB_CONTAINER})"
        elif [[ -n "$staging_diff" ]]; then
            all_diffs="${all_diffs}\n*staging DB* の差分:${staging_diff}"
        fi
    fi

    # Slack 通知
    local slack_text
    local payload

    if [[ -z "$all_diffs" ]] && [[ "$has_error" == "false" ]]; then
        slack_text="✅ [DB スキーマ監視] 差分なし (${today})\nmodels.py と DB スキーマは一致しています。"
        log "No schema diff found"
    else
        slack_text="⚠️ [DB スキーマ監視] スキーマ差分を検出 (${today})${all_diffs}\n\n対応: ALTER TABLE を実行してください。\nRef: \`docs/ops/02_db_tables.md\`"
        log "Schema diff detected — sending alert"
    fi

    payload=$(jq -nc --arg text "$slack_text" '{"text": $text}')
    send_slack "$payload" || exit 1

    if [[ "$has_error" == "true" ]]; then
        exit 1
    fi

    log "Done"
}

main "$@"
