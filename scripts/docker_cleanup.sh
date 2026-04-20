#!/usr/bin/env bash
# scripts/docker_cleanup.sh — 週次 Docker クリーンアップ runbook
#
# 実行内容:
#   1. docker builder prune -f （builder cache 削除）
#   2. docker image prune -f  （dangling image のみ削除、タグ付き image は温存）
#
# 禁止: docker system prune -af は絶対に使わない（CLAUDE.md 明記、使用中 image 削除リスク）
#
# cron 登録例（Hetzner ultra ユーザ）:
#   0 3 * * 0 /opt/ultra-autotrade/scripts/docker_cleanup.sh
#
# 環境変数オーバーライド:
#   DOCKER_CLEANUP_LOG              （デフォルト: /opt/ultra-autotrade/logs/docker_cleanup.log）
#   DOCKER_CLEANUP_ENV_FILE         （デフォルト: /opt/ultra-autotrade/.env.production）
#   DOCKER_CLEANUP_WARN_THRESHOLD   （デフォルト: 70）
#   DOCKER_CLEANUP_CRITICAL_THRESHOLD（デフォルト: 85）
#
# 関連: docs/35_docker_maintenance_runbook.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_FILE="${DOCKER_CLEANUP_LOG:-/opt/ultra-autotrade/logs/docker_cleanup.log}"
ENV_FILE="${DOCKER_CLEANUP_ENV_FILE:-${PROJECT_ROOT}/.env.production}"
WARN_THRESHOLD="${DOCKER_CLEANUP_WARN_THRESHOLD:-70}"
CRITICAL_THRESHOLD="${DOCKER_CLEANUP_CRITICAL_THRESHOLD:-85}"

mkdir -p "$(dirname "${LOG_FILE}")"

# ── ヘルパー ─────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

err() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "${LOG_FILE}" >&2
}

# deploy_production.sh:45-52 と同じインターフェース
# ENV_FILE から SLACK_WEBHOOK_URL を grep 読み込みして curl で送信
slack_notify() {
  local msg="$1"
  local webhook
  webhook="$(grep -E '^SLACK_WEBHOOK_URL=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "${webhook}" ]]; then
    curl -s -X POST "${webhook}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${msg}\"}" >/dev/null || true
  fi
}

# disk 使用率 (%) を整数で返す
get_disk_usage_pct() {
  df / | tail -1 | awk '{gsub(/%/, "", $5); print $5}'
}

# ── メイン処理 ───────────────────────────────────────────────────────────────

log "=== Docker cleanup started ==="

BEFORE_DISK="$(get_disk_usage_pct)"
log "Disk usage BEFORE: ${BEFORE_DISK}%"
log "docker system df BEFORE:"
docker system df 2>&1 | tee -a "${LOG_FILE}"

# 1. Builder cache prune
log "Running: docker builder prune -f"
if ! docker builder prune -f 2>&1 | tee -a "${LOG_FILE}"; then
  err "docker builder prune failed"
  slack_notify ":x: [docker_cleanup] builder prune failed on Hetzner. Check ${LOG_FILE}"
  exit 1
fi

# 2. Dangling image prune（タグなしのみ。タグ付き image は温存）
log "Running: docker image prune -f"
if ! docker image prune -f 2>&1 | tee -a "${LOG_FILE}"; then
  err "docker image prune failed"
  slack_notify ":x: [docker_cleanup] image prune failed on Hetzner. Check ${LOG_FILE}"
  exit 1
fi

AFTER_DISK="$(get_disk_usage_pct)"
log "Disk usage AFTER: ${AFTER_DISK}%"
log "docker system df AFTER:"
docker system df 2>&1 | tee -a "${LOG_FILE}"

# ── 閾値判定 & Slack 通知 ────────────────────────────────────────────────────

LEVEL=":white_check_mark: OK"
if (( AFTER_DISK >= CRITICAL_THRESHOLD )); then
  LEVEL=":rotating_light: CRITICAL"
elif (( AFTER_DISK >= WARN_THRESHOLD )); then
  LEVEL=":warning: WARN"
fi

MSG="${LEVEL} [docker_cleanup] Disk ${BEFORE_DISK}% -> ${AFTER_DISK}% on Hetzner (W=${WARN_THRESHOLD}%, C=${CRITICAL_THRESHOLD}%)"
log "${MSG}"
slack_notify "${MSG}"

log "=== Docker cleanup finished ==="
