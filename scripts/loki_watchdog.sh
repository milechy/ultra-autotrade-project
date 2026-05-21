#!/usr/bin/env bash
# scripts/loki_watchdog.sh — Loki /ready 半死 (empty ring) 自動復旧 watchdog
#
# 背景 (RC-1 / docs/postmortems/2026-05-17_loki_postgres_cascade.md):
#   Loki 2.9.0 single-binary は ingester ring 未登録で `empty ring` 半死状態に陥ることがある
#   (/ready 503 / push 500)。inmemory ring + 127.0.0.1 + replication_factor=1 は標準構成であり
#   config 修正では根治しない既知の ring-init 不安定性。2026-05-17 / 2026-05-21 に発生。
#   #350 で healthcheck (検知) は入ったが、`restart: always` は unhealthy では再起動しないため
#   「検知できても自動復旧しない」穴が残っていた。本 watchdog がその穴を埋める:
#   /ready != 200 を検知したら loki を force-recreate し ingester を ring に再登録させる。
#
# cron 例 (本番 VPS / ultra):
#   */3 * * * * /opt/ultra-autotrade/scripts/loki_watchdog.sh >> /opt/ultra-autotrade/logs/loki_watchdog.log 2>&1
#
# 設計上の安全装置:
#   - COOLDOWN_SEC で recreate 連打を防止 (flap 時の暴走回避)
#   - 検知/復旧の各段階で Slack 通知
#   - recreate は --no-deps で loki 単体のみ (他サービス巻き込み回避)

set -uo pipefail

LOKI_READY_URL="${LOKI_READY_URL:-http://127.0.0.1:3100/ready}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/ultra-autotrade/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
LOKI_SERVICE="${LOKI_SERVICE:-loki}"
DC="${DC:-docker compose}"
CURL_TIMEOUT="${CURL_TIMEOUT:-5}"
COOLDOWN_SEC="${COOLDOWN_SEC:-600}"  # 10分: recreate 連打防止
RECREATE_WAIT_SEC="${RECREATE_WAIT_SEC:-15}"
LAST_RECREATE_FILE="${LAST_RECREATE_FILE:-${TMPDIR:-/tmp}/.loki_watchdog_last_recreate}"

timestamp_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "$(timestamp_utc) [loki_watchdog] $*"; }

# Slack Webhook 解決 (.env.production から)
if [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
  SLACK_WEBHOOK_URL=$(grep "^SLACK_WEBHOOK_URL=" "${ENV_FILE}" | cut -d= -f2- | tr -d '"' || true)
fi

notify() {
  [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
  curl -sf -X POST "${SLACK_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$1\"}" >/dev/null 2>&1 || log "Slack 通知送信失敗"
}

check_ready() {
  curl -s -o /dev/null -w "%{http_code}" --max-time "${CURL_TIMEOUT}" "${LOKI_READY_URL}" 2>/dev/null || echo "000"
}

main() {
  local code
  code=$(check_ready)

  if [[ "${code}" == "200" ]]; then
    log "loki /ready=200 OK"
    return 0
  fi

  log "loki /ready=${code} — 半死 (empty ring) 検知"

  # cooldown チェック (recreate 連打防止)
  local now last elapsed
  now=$(date +%s)
  if [[ -f "${LAST_RECREATE_FILE}" ]]; then
    last=$(cat "${LAST_RECREATE_FILE}" 2>/dev/null || echo "0")
    elapsed=$(( now - last ))
    if (( elapsed < COOLDOWN_SEC )); then
      log "cooldown 中 (前回 recreate から ${elapsed}s < ${COOLDOWN_SEC}s) — recreate スキップ"
      notify ":warning: [loki_watchdog] loki /ready=${code} だが cooldown 中 (${elapsed}s)。連続発生のため手動調査推奨"
      return 1
    fi
  fi

  log "loki を force-recreate (ingester ring 再登録)"
  notify ":rotating_light: [loki_watchdog] loki /ready=${code} 検知 → force-recreate 実行 (RC-1 empty ring 自動復旧)"

  if ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps --force-recreate "${LOKI_SERVICE}" >/dev/null 2>&1; then
    echo "${now}" > "${LAST_RECREATE_FILE}" 2>/dev/null || true
    sleep "${RECREATE_WAIT_SEC}"
    local newcode
    newcode=$(check_ready)
    log "recreate 後 /ready=${newcode}"
    if [[ "${newcode}" == "200" ]]; then
      notify ":white_check_mark: [loki_watchdog] loki recreate 成功、/ready=200 復旧"
      return 0
    fi
    notify ":x: [loki_watchdog] loki recreate 後も /ready=${newcode}。手動調査が必要"
    return 1
  fi

  log "docker compose recreate 失敗"
  notify ":x: [loki_watchdog] loki recreate コマンド失敗。手動対応が必要"
  return 1
}

main "$@"
