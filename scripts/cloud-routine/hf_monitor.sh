#!/usr/bin/env bash
# scripts/cloud-routine/hf_monitor.sh
#
# Ultra AutoTrade — Aave V3 Health Factor 監視スクリプト
#
# 機能:
#   - Hetzner VPS の backend API 経由で Aave Health Factor を取得
#   - HF < 1.8: Slack 警告通知
#   - HF < 1.6: Slack アラート通知 + 緊急停止フラグ確認を促す
#
# 必須環境変数:
#   SLACK_WEBHOOK_URL     Slack Incoming Webhook URL
#   INTERNAL_API_TOKEN    backend 内部 API トークン
#
# オプション環境変数:
#   BACKEND_URL           backend URL (default: https://api.ultra-auto-trade.com)
#   HF_WARN_THRESHOLD     警告閾値 (default: 1.8)
#   HF_ALERT_THRESHOLD    アラート閾値 (default: 1.6)
#   DRY_RUN               "true" のとき Slack 通知をスキップ
#
# 実行例:
#   INTERNAL_API_TOKEN=xxx SLACK_WEBHOOK_URL=https://... ./hf_monitor.sh
#
# Hetzner から SSH 経由で実行する場合:
#   ssh hetzner 'cd /opt/ultra-autotrade && bash scripts/cloud-routine/hf_monitor.sh'
#
# cron 設定例 (15 分間隔、Hetzner cron):
#   */15 * * * * cd /opt/ultra-autotrade && \
#     INTERNAL_API_TOKEN=$(grep INTERNAL_API_TOKEN .env.production | cut -d= -f2-) \
#     SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
#     bash scripts/cloud-routine/hf_monitor.sh >> /var/log/ultra/hf_monitor.log 2>&1
#
# Mac から cron でリモート実行する場合 (launchd 例は README.md 参照):
#   */15 * * * * ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 \
#     'cd /opt/ultra-autotrade && env $(grep -v "^#" .env.production | xargs) \
#     bash scripts/cloud-routine/hf_monitor.sh'

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
BACKEND_URL="${BACKEND_URL:-https://api.ultra-auto-trade.com}"
AAVE_STATUS_ENDPOINT="${BACKEND_URL}/api/aave/status"
HF_WARN_THRESHOLD="${HF_WARN_THRESHOLD:-1.8}"
HF_ALERT_THRESHOLD="${HF_ALERT_THRESHOLD:-1.6}"
DRY_RUN="${DRY_RUN:-false}"
SCRIPT_NAME="hf_monitor"
TIMEOUT=15

# =============================================================================
# ユーティリティ
# =============================================================================
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SCRIPT_NAME] $*"; }
log_warn() { log "WARN $*"; }
log_error() { log "ERROR $*"; }

check_deps() {
    local missing=0
    for cmd in curl jq bc; do
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
    if [[ -z "${INTERNAL_API_TOKEN:-}" ]]; then
        log_error "INTERNAL_API_TOKEN is not set"
        missing=1
    fi
    return $missing
}

# =============================================================================
# Health Factor 取得
# =============================================================================
fetch_health_factor() {
    local response
    local http_code

    response=$(curl -sf \
        --max-time "$TIMEOUT" \
        -H "Authorization: Bearer ${INTERNAL_API_TOKEN}" \
        -H "Accept: application/json" \
        -w "\n%{http_code}" \
        "${AAVE_STATUS_ENDPOINT}" 2>/dev/null) || {
        log_error "Failed to connect to backend: ${AAVE_STATUS_ENDPOINT}"
        echo "ERROR"
        return 1
    }

    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | head -n -1)

    if [[ "$http_code" != "200" ]]; then
        log_error "Backend returned HTTP ${http_code}"
        echo "ERROR"
        return 1
    fi

    local hf
    hf=$(echo "$body" | jq -r '.health_factor // empty' 2>/dev/null)

    if [[ -z "$hf" || "$hf" == "null" ]]; then
        log "No active Aave position (health_factor not available)"
        echo "NO_POSITION"
        return 0
    fi

    echo "$hf"
}

# =============================================================================
# 閾値比較 (bc 使用でfloat比較)
# =============================================================================
is_below() {
    local value="$1"
    local threshold="$2"
    [[ "$(echo "$value < $threshold" | bc -l)" == "1" ]]
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
    log "Start Health Factor monitoring"

    check_deps || exit 1
    check_env || exit 1

    local hf
    hf=$(fetch_health_factor) || exit 1

    case "$hf" in
        "ERROR")
            local payload
            payload=$(jq -nc '{"text": "❌ [HF監視] backend API に接続できませんでした。バックエンドの状態を確認してください。"}')
            send_slack "$payload"
            exit 1
            ;;
        "NO_POSITION")
            log "No active Aave position — no notification needed"
            exit 0
            ;;
    esac

    log "Current Health Factor: ${hf}"

    local slack_text
    local payload

    if is_below "$hf" "$HF_ALERT_THRESHOLD"; then
        # HF < 1.6: アラート
        slack_text="🚨 *[HF アラート]* Aave Health Factor が危険水域です！\n\n*HF: ${hf}* (閾値: ${HF_ALERT_THRESHOLD})\n\n⚠️ 緊急停止フラグを確認してください:\n\`curl -sf https://api.ultra-auto-trade.com/health | jq '.emergency_stop'\`\n\n即座に対応が必要です。"
        log "ALERT: HF ${hf} is below alert threshold ${HF_ALERT_THRESHOLD}"
    elif is_below "$hf" "$HF_WARN_THRESHOLD"; then
        # HF < 1.8: 警告
        slack_text="⚠️ [HF 警告] Aave Health Factor が低下しています。\n\n*HF: ${hf}* (警告閾値: ${HF_WARN_THRESHOLD})\n\nポジションを監視してください。"
        log "WARN: HF ${hf} is below warning threshold ${HF_WARN_THRESHOLD}"
    else
        log "HF ${hf} is healthy (>= ${HF_WARN_THRESHOLD}) — no notification"
        exit 0
    fi

    payload=$(jq -nc --arg text "$slack_text" '{"text": $text}')
    send_slack "$payload" || exit 1

    log "Done"
}

main "$@"
