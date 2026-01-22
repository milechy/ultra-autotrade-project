#!/usr/bin/env bash
set -euo pipefail

# scripts/monitor.sh
#
# Ultra AutoTrade の簡易監視スクリプト。
# - /health の死活監視
# - レイテンシをメトリクスログとして出力
#
# 用途:
#   monitor.sh daily   # 日次チェック（cron から呼ぶ）
#   monitor.sh weekly  # 週次チェック（cron から呼ぶ）

MODE="${1:-daily}"

BACKEND_HEALTH_URL="${MONITOR_HEALTHCHECK_URL:-http://localhost:8000/health}"
METRICS_LOG_DIR="${METRICS_LOG_DIR:-/var/log/ultra}"
mkdir -p "${METRICS_LOG_DIR}"

LOG_FILE="${METRICS_LOG_DIR}/monitor_${MODE}.log"
METRICS_LOG_FILE="${METRICS_LOG_DIR}/metrics.log"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  echo "$(timestamp) [monitor:${MODE}] $*" | tee -a "${LOG_FILE}"
}

check_health() {
  local start end status latency_ms

  start=$(date +%s%3N)
  # -s: silent, -o /dev/null: body 捨てる, -w '%{http_code}': ステータスのみ出力
  status=$(curl -s -o /dev/null -w '%{http_code}' "${BACKEND_HEALTH_URL}" || echo "000")
  end=$(date +%s%3N)

  latency_ms=$((end - start))

  log "health_check status=${status} latency_ms=${latency_ms}"

  # メトリクスログ (JSON Lines 形式に近いもの)
  printf '%s\t%s\t%s\n' \
    "$(timestamp)" \
    "backend_http_latency_p95_ms" \
    "${latency_ms}" >> "${METRICS_LOG_FILE}"

  if [[ "${status}" -ne 200 ]]; then
    log "ERROR: health check failed (status=${status})"
    return 1
  fi

  return 0
}

case "${MODE}" in
  daily)
    log "starting daily monitor"
    check_health
    log "finished daily monitor"
    ;;

  weekly)
    log "starting weekly monitor"
    check_health
    log "finished weekly monitor"
    ;;

  *)
    echo "Usage: $0 {daily|weekly}" >&2
    exit 2
    ;;
esac
