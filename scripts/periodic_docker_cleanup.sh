#!/usr/bin/env bash
# scripts/periodic_docker_cleanup.sh — 週次 Docker + journal 積極クリーンアップ
#
# docker_cleanup.sh (dangling のみ) より積極的なクリーンアップを実施:
#   1. docker builder prune -a -f  (ALL builder cache 削除)
#   2. docker image prune -f       (dangling image のみ削除、タグ付き image は温存)
#   3. journalctl --vacuum-size=1G (systemd journal を 1GB 以下に圧縮)
#
# 禁止: docker system prune -af は絶対に使わない (使用中 image 削除リスク / CLAUDE.md 明記)
#
# cron 登録例 (Hetzner ultra ユーザ):
#   0 3 * * 0 /opt/ultra-autotrade/scripts/periodic_docker_cleanup.sh >> /var/log/ultra-autotrade/periodic_cleanup.log 2>&1
#
# 環境変数オーバーライド:
#   PERIODIC_CLEANUP_LOG              (デフォルト: /opt/ultra-autotrade/logs/periodic_cleanup.log)
#   PERIODIC_CLEANUP_ENV_FILE         (デフォルト: /opt/ultra-autotrade/.env.production)
#   PERIODIC_CLEANUP_WARN_THRESHOLD   (デフォルト: 80)
#   PERIODIC_CLEANUP_CRITICAL_THRESHOLD (デフォルト: 90)
#   JOURNAL_VACUUM_SIZE               (デフォルト: 1G)
#   DRY_RUN                           (true の場合 prune 実行せず Slack 通知もスキップ)
#
# 関連: docs/35_docker_maintenance_runbook.md, scripts/docker_cleanup.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_FILE="${PERIODIC_CLEANUP_LOG:-/opt/ultra-autotrade/logs/periodic_cleanup.log}"
ENV_FILE="${PERIODIC_CLEANUP_ENV_FILE:-${PROJECT_ROOT}/.env.production}"
WARN_THRESHOLD="${PERIODIC_CLEANUP_WARN_THRESHOLD:-80}"
CRITICAL_THRESHOLD="${PERIODIC_CLEANUP_CRITICAL_THRESHOLD:-90}"
JOURNAL_VACUUM_SIZE="${JOURNAL_VACUUM_SIZE:-1G}"
DRY_RUN="${DRY_RUN:-false}"

mkdir -p "$(dirname "${LOG_FILE}")"

# ── ヘルパー ─────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

err() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "${LOG_FILE}" >&2
}

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

get_disk_usage_pct() {
  df / | tail -1 | awk '{gsub(/%/, "", $5); print $5}'
}

get_disk_avail_gb() {
  df -BG / | tail -1 | awk '{gsub(/G/, "", $4); print $4}'
}

# ── メイン処理 ───────────────────────────────────────────────────────────────

log "=== periodic_docker_cleanup started ==="

BEFORE_DISK="$(get_disk_usage_pct)"
BEFORE_AVAIL="$(get_disk_avail_gb)"
log "Disk BEFORE: ${BEFORE_DISK}% used (avail: ${BEFORE_AVAIL}G)"
log "docker system df BEFORE:"
docker system df 2>&1 | tee -a "${LOG_FILE}"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY_RUN] スキップ: docker builder prune -a -f"
  log "[DRY_RUN] スキップ: docker image prune -f"
  log "[DRY_RUN] スキップ: journalctl --vacuum-size=${JOURNAL_VACUUM_SIZE}"
else
  # 1. ALL builder cache prune (docker_cleanup.sh より積極的: -a フラグ付き)
  log "Running: docker builder prune -a -f"
  if ! docker builder prune -a -f 2>&1 | tee -a "${LOG_FILE}"; then
    err "docker builder prune -a failed"
    slack_notify ":x: [periodic_cleanup] builder prune -a failed on Hetzner. Check ${LOG_FILE}"
    exit 1
  fi

  # 2. Dangling image prune (タグなしのみ。タグ付き image は温存)
  log "Running: docker image prune -f"
  if ! docker image prune -f 2>&1 | tee -a "${LOG_FILE}"; then
    err "docker image prune failed"
    slack_notify ":x: [periodic_cleanup] image prune failed on Hetzner. Check ${LOG_FILE}"
    exit 1
  fi

  # 3. systemd journal vacuum (1GB 以下に圧縮)
  log "Running: journalctl --vacuum-size=${JOURNAL_VACUUM_SIZE}"
  if command -v journalctl &>/dev/null; then
    if ! journalctl --vacuum-size="${JOURNAL_VACUUM_SIZE}" 2>&1 | tee -a "${LOG_FILE}"; then
      err "journalctl vacuum failed (non-fatal)"
      slack_notify ":warning: [periodic_cleanup] journalctl vacuum failed on Hetzner. Check ${LOG_FILE}"
      # journal vacuum 失敗は非致命的 — continue
    fi
  else
    log "journalctl not found — スキップ (非 systemd 環境)"
  fi
fi

AFTER_DISK="$(get_disk_usage_pct)"
AFTER_AVAIL="$(get_disk_avail_gb)"
log "Disk AFTER: ${AFTER_DISK}% used (avail: ${AFTER_AVAIL}G)"
log "docker system df AFTER:"
docker system df 2>&1 | tee -a "${LOG_FILE}"

# ── 閾値判定 & Slack 通知 ────────────────────────────────────────────────────

LEVEL=":white_check_mark: OK"
if (( AFTER_DISK >= CRITICAL_THRESHOLD )); then
  LEVEL=":rotating_light: CRITICAL"
elif (( AFTER_DISK >= WARN_THRESHOLD )); then
  LEVEL=":warning: WARN"
fi

FREED=$(( BEFORE_DISK - AFTER_DISK ))
MSG="${LEVEL} [periodic_cleanup] Disk ${BEFORE_DISK}%→${AFTER_DISK}% (freed ${FREED}%, avail ${AFTER_AVAIL}G) on Hetzner"
log "${MSG}"

if [[ "${DRY_RUN}" != "true" ]]; then
  slack_notify "${MSG}"

  # CRITICAL 時は追加の詳細通知
  if (( AFTER_DISK >= CRITICAL_THRESHOLD )); then
    DETAIL=":rotating_light: [periodic_cleanup] ディスク使用率 ${AFTER_DISK}% — クリーンアップ後も CRITICAL。手動調査が必要です。\n\`docker system df\` / \`df -h\` で確認してください。"
    slack_notify "${DETAIL}"
    err "Disk still CRITICAL (${AFTER_DISK}%) after cleanup — manual action required"
    exit 2
  fi
fi

log "=== periodic_docker_cleanup finished ==="
