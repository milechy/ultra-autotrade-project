#!/usr/bin/env bash
# staging-watchdog.sh — staging-new stack の死活監視 + 自動復旧
#
# cron 登録例 (5分ごと):
#   */5 * * * * /opt/ultra-autotrade/scripts/staging-watchdog.sh >> /var/log/ultra-autotrade/staging-watchdog.log 2>&1
#
# 真因: deploy_production.sh の down --remove-orphans が staging-new を道連れ削除していた
# 根本修正: deploy_production.sh から --remove-orphans を除去 (fix/staging-orphan-protection-20260520)
# 本スクリプト: defense-in-depth として staging 停止時に自動 up -d する

set -euo pipefail

COMPOSE_DIR="/opt/ultra-autotrade"
COMPOSE_FILE="docker-compose.staging.yml"
ENV_FILE=".env.staging-new"
SENTINEL_CONTAINER="ultra-autotrade-postgres-staging-new"
LOG_PREFIX="[staging-watchdog] $(date '+%Y-%m-%dT%H:%M:%S')"
WEBHOOK_FILE="${COMPOSE_DIR}/.env.production"

notify_slack() {
  local msg="$1"
  local webhook
  webhook=$(grep "^SLACK_WEBHOOK_URL=" "${WEBHOOK_FILE}" 2>/dev/null | cut -d= -f2- || true)
  if [[ -n "${webhook}" ]]; then
    curl -sf -X POST "${webhook}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${msg}\"}" >/dev/null 2>&1 || true
  fi
}

# postgres コンテナが Up かどうか確認
is_staging_alive() {
  docker ps --filter "name=${SENTINEL_CONTAINER}" --filter "status=running" -q | grep -q .
}

if is_staging_alive; then
  echo "${LOG_PREFIX} staging healthy (${SENTINEL_CONTAINER} running)"
  exit 0
fi

echo "${LOG_PREFIX} WARN: staging stack down — starting auto-recovery"
notify_slack "⚠️ [staging-watchdog] staging stack 停止を検知。自動復旧を開始します。"

cd "${COMPOSE_DIR}"
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d 2>&1

# 15秒待って確認
sleep 15

if is_staging_alive; then
  echo "${LOG_PREFIX} RECOVERED: staging stack restored"
  notify_slack "✅ [staging-watchdog] staging stack 自動復旧完了。"
else
  echo "${LOG_PREFIX} ERROR: staging stack recovery FAILED"
  notify_slack "❌ [staging-watchdog] staging stack 自動復旧失敗。手動対応が必要です。"
  exit 1
fi
