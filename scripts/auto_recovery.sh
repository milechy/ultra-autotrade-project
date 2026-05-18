#!/usr/bin/env bash
# scripts/auto_recovery.sh
#
# Ultra AutoTrade 自動復旧スクリプト (プロトタイプ)
# 設計仕様: docs/auto_recovery_scope.md
#
# [注意] 本スクリプトは Tier B 設計ドキュメントに対応するプロトタイプ。
#         本番 Hetzner への配置は別途 Tier S タスクで実施する。
#
# 使い方:
#   DRY_RUN=true bash scripts/auto_recovery.sh --check-all   # 全チェック (空振り)
#   bash scripts/auto_recovery.sh --action nginx-restart     # nginx のみ復旧
#   bash scripts/auto_recovery.sh --action backend-restart   # backend のみ復旧
#
# 環境変数:
#   DRY_RUN                true の場合 docker コマンドを実行しない (デフォルト: false)
#   UATA_CONFIG            ~/.claude-uata (デフォルト)
#   HEALTH_URL_INTERNAL    http://127.0.0.1:8010/health (デフォルト)
#   HEALTH_URL_EXTERNAL    https://api.ultra-auto-trade.com/health (デフォルト)
#   RECOVERY_LOG           $UATA_CONFIG/logs/auto_recovery.log

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
UATA_CONFIG="${UATA_CONFIG:-$HOME/.claude-uata}"
RECOVERY_LOG="${RECOVERY_LOG:-$UATA_CONFIG/logs/auto_recovery.log}"
COOLDOWN_DIR="${COOLDOWN_DIR:-$UATA_CONFIG/recovery-cooldown}"
DRY_RUN="${DRY_RUN:-false}"

HEALTH_URL_INTERNAL="${HEALTH_URL_INTERNAL:-http://127.0.0.1:8010/health}"
HEALTH_URL_EXTERNAL="${HEALTH_URL_EXTERNAL:-https://api.ultra-auto-trade.com/health}"
CURL_TIMEOUT=10

# コンテナ名 (production)
CONTAINER_BACKEND="ultra-autotrade-backend-production"
CONTAINER_NGINX="ultra-autotrade-nginx-production"
CONTAINER_CLOUDFLARED="ultra-autotrade-cloudflared-production"
CONTAINER_POSTGRES="ultra-autotrade-postgres-production"

# クールダウン設定 (1時間スライディングウィンドウ)
COOLDOWN_WINDOW_SEC=3600
declare -A COOLDOWN_MAX=(
    ["nginx"]=3
    ["backend"]=3
    ["cloudflared"]=3
    ["scheduler"]=2
)

mkdir -p "$(dirname "$RECOVERY_LOG")" "$COOLDOWN_DIR"
exec >> "$RECOVERY_LOG" 2>&1

# =============================================================================
# ユーティリティ
# =============================================================================
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "$(ts) [auto_recovery] $*"; }

send_slack() {
    local text="$1"
    local env_file="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
    local webhook=""
    if [[ -f "$env_file" ]]; then
        webhook=$(grep "^SLACK_WEBHOOK_URL=" "$env_file" | cut -d= -f2- | tr -d '"' || true)
    fi
    [[ -z "$webhook" ]] && { log "SLACK_WEBHOOK_URL 未設定 — Slack 通知スキップ"; return 0; }
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY_RUN] Slack: $text"; return 0
    fi
    curl -sf -X POST "$webhook" -H "Content-Type: application/json" \
        -d "{\"text\": \"$text\"}" > /dev/null || log "Slack 通知失敗"
}

# Pushover 通知 (scripts/uata-pushover-notify.sh に委譲)
pushover_critical() {
    local title="$1" message="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY_RUN] Pushover CRITICAL: $title — $message"; return 0
    fi
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$script_dir/uata-pushover-notify.sh" ]]; then
        # shellcheck disable=SC1090
        source "$script_dir/uata-pushover-notify.sh" 2>/dev/null || true
        uata_notify_critical "$title" "$message" 2>/dev/null || log "Pushover 送信失敗: $title"
    else
        log "uata-pushover-notify.sh not found — Pushover スキップ"
    fi
}

pushover_high() {
    local title="$1" message="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY_RUN] Pushover HIGH: $title — $message"; return 0
    fi
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$script_dir/uata-pushover-notify.sh" ]]; then
        # shellcheck disable=SC1090
        source "$script_dir/uata-pushover-notify.sh" 2>/dev/null || true
        uata_notify_high "$title" "$message" 2>/dev/null || log "Pushover 送信失敗: $title"
    fi
}

# =============================================================================
# クールダウン管理
# =============================================================================

# 過去 COOLDOWN_WINDOW_SEC 内の restart 回数を返す
cooldown_count() {
    local target="$1"
    local now window_start count=0
    now=$(date +%s)
    window_start=$(( now - COOLDOWN_WINDOW_SEC ))
    for f in "$COOLDOWN_DIR/${target}"-*.ts; do
        [[ -f "$f" ]] || continue
        local ts_val
        ts_val=$(cat "$f" 2>/dev/null || echo 0)
        if [[ "$ts_val" -ge "$window_start" ]]; then
            count=$(( count + 1 ))
        else
            rm -f "$f"
        fi
    done
    echo "$count"
}

# クールダウン記録
cooldown_record() {
    local target="$1"
    echo "$(date +%s)" > "$COOLDOWN_DIR/${target}-$(date +%s%N).ts"
}

# クールダウン上限チェック (true=上限超過)
cooldown_exceeded() {
    local target="$1"
    local max="${COOLDOWN_MAX[$target]:-3}"
    local count
    count=$(cooldown_count "$target")
    log "クールダウンカウント: $target=$count/$max"
    [[ "$count" -ge "$max" ]]
}

# =============================================================================
# ヘルスチェックユーティリティ
# =============================================================================

check_internal_health() {
    curl -sf --connect-timeout "$CURL_TIMEOUT" --max-time "$CURL_TIMEOUT" \
        "$HEALTH_URL_INTERNAL" > /dev/null 2>&1
}

check_external_health() {
    local code
    code=$(curl -s --connect-timeout "$CURL_TIMEOUT" --max-time "$CURL_TIMEOUT" \
        -o /dev/null -w "%{http_code}" "$HEALTH_URL_EXTERNAL" 2>/dev/null)
    [[ "$code" == "200" ]]
}

container_state() {
    local name="$1"
    docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "not_found"
}

container_health() {
    local name="$1"
    docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "none"
}

# =============================================================================
# 復旧アクション
# =============================================================================

# AR-1 / AR-4: コンテナ restart
do_restart() {
    local target="$1" container="$2" verify_fn="$3" wait_sec="${4:-30}"

    log "[$target] restart 開始: $container"

    if cooldown_exceeded "$target"; then
        log "[$target] クールダウン上限超過 → 自動復旧停止"
        pushover_critical "UATa 自動復旧停止: $target" \
            "1時間に${COOLDOWN_MAX[$target]:-3}回 restart しても復旧しません。手動確認が必要です。container=$container"
        send_slack "🚨 [auto_recovery] *$target クールダウン上限到達*: 自動復旧を停止しました。container=$container"
        return 1
    fi

    cooldown_record "$target"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY_RUN] docker restart $container"
    else
        docker restart "$container" || {
            log "[$target] docker restart 失敗"
            send_slack "❌ [auto_recovery] $target docker restart 失敗: $container"
            return 1
        }
    fi

    log "[$target] restart 完了。${wait_sec}秒待機して検証..."
    sleep "$wait_sec"

    if $verify_fn; then
        log "[$target] 復旧確認: OK"
        send_slack "✅ [auto_recovery] *$target 自動復旧成功*: $container を restart しました。$(ts)"
        return 0
    else
        log "[$target] 復旧確認: FAIL — restart したが復旧していない"
        pushover_critical "UATa 自動復旧失敗: $target" \
            "$container を restart しましたが復旧していません。手動確認が必要です。"
        send_slack "❌ [auto_recovery] $target restart 後も復旧せず: $container"
        return 1
    fi
}

# AR-1: nginx restart
action_nginx_restart() {
    do_restart "nginx" "$CONTAINER_NGINX" check_external_health 30
}

# AR-2 / AR-3: backend restart
action_backend_restart() {
    do_restart "backend" "$CONTAINER_BACKEND" check_internal_health 60
}

# AR-4: cloudflared restart
action_cloudflared_restart() {
    do_restart "cloudflared" "$CONTAINER_CLOUDFLARED" check_external_health 60
}

# =============================================================================
# 判断ロジック (healthcheck_l1_l6.sh からの呼び出し用)
# =============================================================================

# L1 FAIL 時のトリアージ
triage_l1_fail() {
    log "L1 FAIL トリアージ開始"

    # postgres チェック (HR-1: 人間必須)
    local pg_state
    pg_state=$(container_state "$CONTAINER_POSTGRES")
    if [[ "$pg_state" != "running" ]]; then
        log "postgres が $pg_state — HR-1: 人間必須"
        pushover_critical "UATa CRITICAL: postgres $pg_state" \
            "postgres コンテナが $pg_state です。手動復旧が必要です。docs/31_backup_restore_procedures.md 参照。"
        send_slack "🚨 [auto_recovery] *postgres $pg_state*: 自動復旧不可。手動確認必須。"
        return 0
    fi

    # 複数コンテナ down チェック (HR-4)
    local up_count
    up_count=$(docker ps --filter "name=ultra-autotrade" --filter "status=running" \
        --format "{{.Names}}" 2>/dev/null | wc -l | tr -d '[:space:]')
    if [[ "${up_count:-0}" -lt 5 ]]; then
        log "コンテナ $up_count/7 Up — HR-4: 人間必須"
        pushover_critical "UATa CRITICAL: $up_count コンテナのみ Up" \
            "通常7コンテナのところ $up_count しか Up していません。複合障害の可能性があります。"
        send_slack "🚨 [auto_recovery] *複数コンテナ down* ($up_count/7 Up): 自動復旧不可。手動確認必須。"
        return 0
    fi

    # 内部 200 + 外形 non-200 → nginx or cloudflared の問題
    if check_internal_health && ! check_external_health; then
        log "内部 OK / 外形 FAIL — cloudflared or nginx チェック"

        local cf_state
        cf_state=$(container_state "$CONTAINER_CLOUDFLARED")
        if [[ "$cf_state" == "exited" ]]; then
            log "cloudflared exited → AR-4 実行"
            action_cloudflared_restart
            return $?
        fi

        log "cloudflared は Running → nginx IP 固着の可能性 → AR-1 実行"
        action_nginx_restart
        return $?
    fi

    # backend unhealthy
    local be_health
    be_health=$(container_health "$CONTAINER_BACKEND")
    local be_state
    be_state=$(container_state "$CONTAINER_BACKEND")
    if [[ "$be_health" == "unhealthy" ]] || [[ "$be_state" == "exited" ]]; then
        log "backend $be_state/$be_health → AR-2 実行"
        action_backend_restart
        return $?
    fi

    log "L1 FAIL 原因特定不可 — Slack 通知のみ"
    send_slack "⚠️ [auto_recovery] L1 FAIL だが原因特定不可。手動確認してください。"
}

# L2 FAIL 時のトリアージ
triage_l2_fail() {
    log "L2 FAIL トリアージ開始"

    local be_state
    be_state=$(container_state "$CONTAINER_BACKEND")
    if [[ "$be_state" == "running" ]]; then
        log "backend は Running かつ scheduler dead → AR-3 実行"
        do_restart "scheduler" "$CONTAINER_BACKEND" check_internal_health 90
    else
        log "backend が $be_state — triage_l1_fail に移譲"
        triage_l1_fail
    fi
}

# L3 FAIL + L2 PASS → HR-6
triage_l3_fail_l2_pass() {
    log "L3 FAIL (AI 判定 0件) + L2 PASS — HR-6: Pushover HIGH"
    pushover_high "UATa: AI 判定 24h ゼロ" \
        "scheduler は生存していますが、24h AI 判定が出ていません。コード・設定の確認が必要です。"
    send_slack "⚠️ [auto_recovery] AI 判定 24h ゼロ (L3 FAIL)。scheduler は生存中。手動確認推奨。"
}

# 全体チェック & トリアージ (healthcheck_l1_l6.sh からの呼び出し想定)
check_all() {
    log "=== 全体チェック開始 ==="

    # disk チェック (Linux/macOS 両対応)
    local disk_pct
    disk_pct=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/, "", $5); print $5}' || echo "0")
    if [[ "${disk_pct:-0}" -ge 85 ]]; then
        log "disk $disk_pct% > 85% — HR-5: Pushover HIGH"
        pushover_high "UATa: disk 使用率 ${disk_pct}%" \
            "disk 使用率が $disk_pct% です。docker_cleanup.sh の手動実行を検討してください。"
        send_slack "⚠️ [auto_recovery] disk 使用率 $disk_pct%。docs/35_docker_maintenance_runbook.md 参照。"
    fi

    log "=== 全体チェック完了 ==="
}

# =============================================================================
# CLI エントリーポイント
# =============================================================================
usage() {
    cat <<EOF
使い方: $0 [オプション]

オプション:
  --check-all                   全体チェック実行 (disk, etc.)
  --action nginx-restart        AR-1: nginx restart
  --action backend-restart      AR-2/AR-3: backend restart
  --action cloudflared-restart  AR-4: cloudflared restart
  --triage-l1                   L1 FAIL トリアージ
  --triage-l2                   L2 FAIL トリアージ
  --triage-l3-l2-pass           L3 FAIL + L2 PASS → Pushover HIGH

環境変数:
  DRY_RUN=true  docker コマンドを実行せず、ログのみ出力

例:
  DRY_RUN=true bash scripts/auto_recovery.sh --check-all
  bash scripts/auto_recovery.sh --triage-l1
EOF
}

main() {
    local action="${1:-}"

    case "$action" in
        --check-all)
            check_all
            ;;
        --action)
            case "${2:-}" in
                nginx-restart)       action_nginx_restart ;;
                backend-restart)     action_backend_restart ;;
                cloudflared-restart) action_cloudflared_restart ;;
                *)                   echo "不明なアクション: ${2:-}"; usage; exit 1 ;;
            esac
            ;;
        --triage-l1)      triage_l1_fail ;;
        --triage-l2)      triage_l2_fail ;;
        --triage-l3-l2-pass) triage_l3_fail_l2_pass ;;
        --help|-h)        usage ;;
        *)
            log "引数なし — check_all のみ実行"
            check_all
            ;;
    esac
}

main "$@"
