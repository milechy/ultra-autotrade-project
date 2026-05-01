#!/usr/bin/env bash
# scripts/cloud-routine/expired_tasks_monitor.sh
#
# Ultra AutoTrade — Asana 期限超過タスク監視スクリプト
#
# 機能:
#   - 複数 Asana プロジェクトの期限超過タスクを検出
#   - Slack #ultra-auto-project に件数と上位 5 件を通知
#
# 必須環境変数:
#   ASANA_PAT            Asana Personal Access Token
#   SLACK_WEBHOOK_URL    Slack Incoming Webhook URL
#
# オプション環境変数:
#   DRY_RUN              "true" のとき Slack 通知をスキップ（ログのみ）
#   MAX_REPORT_TASKS     通知する上位タスク数 (default: 5)
#
# 実行例:
#   ASANA_PAT=xxx SLACK_WEBHOOK_URL=https://... ./expired_tasks_monitor.sh
#
# cron 設定例 (毎朝 8:00 JST = 23:00 UTC):
#   0 23 * * * cd /opt/ultra-autotrade && \
#     ASANA_PAT=$(grep ASANA_PAT .env.production | cut -d= -f2-) \
#     SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
#     bash scripts/cloud-routine/expired_tasks_monitor.sh >> /var/log/ultra/expired_tasks_monitor.log 2>&1

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
ASANA_API="https://app.asana.com/api/1.0"
MAX_REPORT_TASKS="${MAX_REPORT_TASKS:-5}"
DRY_RUN="${DRY_RUN:-false}"
SCRIPT_NAME="expired_tasks_monitor"

# 監視対象プロジェクト GID 一覧
PROJECT_GIDS=(
    "1213996126630018"
    "1213880674050095"
    "1213829744814355"
    "1213741124336104"
    "1213741363139523"
    "1213814438308045"
    "1213750720428321"
    "1213814721653249"
)

# =============================================================================
# ユーティリティ
# =============================================================================
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SCRIPT_NAME] $*"; }
log_warn() { log "WARN $*"; }
log_error() { log "ERROR $*"; }

check_deps() {
    local missing=0
    for cmd in curl jq date; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log_error "Required command not found: $cmd"
            missing=1
        fi
    done
    return $missing
}

check_env() {
    local missing=0
    if [[ -z "${ASANA_PAT:-}" ]]; then
        log_error "ASANA_PAT is not set"
        missing=1
    fi
    if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
        log_error "SLACK_WEBHOOK_URL is not set"
        missing=1
    fi
    return $missing
}

# =============================================================================
# Asana API 呼び出し
# =============================================================================
asana_get() {
    local endpoint="$1"
    curl -sf \
        --max-time 15 \
        -H "Authorization: Bearer ${ASANA_PAT}" \
        -H "Accept: application/json" \
        "${ASANA_API}${endpoint}"
}

# 指定プロジェクトの期限超過タスクを取得
fetch_expired_tasks() {
    local project_gid="$1"
    local today
    today=$(date -u '+%Y-%m-%d')

    local response
    if ! response=$(asana_get \
        "/tasks?project=${project_gid}&completed_since=now&opt_fields=name,due_on,assignee.name&limit=100" \
        2>/dev/null); then
        log_warn "Failed to fetch tasks for project ${project_gid}"
        echo "[]"
        return
    fi

    # due_on が today より前のタスクのみ抽出
    echo "$response" | jq --arg today "$today" \
        '[.data[] | select(.due_on != null and .due_on < $today)]' 2>/dev/null || echo "[]"
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
    log "Start expired tasks monitoring ($(date '+%Y-%m-%d %H:%M JST'))"

    check_deps || exit 1
    check_env || exit 1

    local total_expired=0
    local task_lines=""
    local today
    today=$(date -u '+%Y-%m-%d')

    for gid in "${PROJECT_GIDS[@]}"; do
        log "Checking project ${gid}..."
        local tasks
        tasks=$(fetch_expired_tasks "$gid")

        local count
        count=$(echo "$tasks" | jq 'length' 2>/dev/null || echo "0")
        total_expired=$((total_expired + count))

        if [[ "$count" -gt 0 ]]; then
            local lines
            lines=$(echo "$tasks" | jq -r \
                '.[] | "  • \(.name) [期限: \(.due_on)] 担当: \(.assignee.name // "未割当")"' \
                2>/dev/null || true)
            task_lines="${task_lines}${lines}"$'\n'
        fi
        log "  -> ${count} expired tasks in project ${gid}"
    done

    log "Total expired tasks: ${total_expired}"

    # 上位 MAX_REPORT_TASKS 件に絞る
    local top_tasks=""
    if [[ -n "$task_lines" ]]; then
        top_tasks=$(echo "$task_lines" | head -n "${MAX_REPORT_TASKS}")
    fi

    # Slack メッセージ生成
    local slack_text
    if [[ "$total_expired" -eq 0 ]]; then
        slack_text="✅ [Asana 期限監視] 期限超過タスク: 0 件 (${today})"
        log "No expired tasks found — sending OK notification"
    else
        slack_text="⚠️ [Asana 期限監視] 期限超過タスク: *${total_expired} 件* (${today})\n\n上位 ${MAX_REPORT_TASKS} 件:\n${top_tasks}\n\n<https://app.asana.com/|Asana で確認>"
        log "Expired tasks found — sending alert notification"
    fi

    local payload
    payload=$(jq -nc --arg text "$slack_text" '{"text": $text}')
    send_slack "$payload" || exit 1

    log "Done"
}

main "$@"
