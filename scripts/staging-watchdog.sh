#!/usr/bin/env bash
# staging-watchdog.sh — staging-new stack の死活監視 + 自動復旧
#
# cron 登録例 (5分ごと):
#   */5 * * * * /opt/ultra-autotrade/scripts/staging-watchdog.sh >> /var/log/ultra-autotrade/staging-watchdog.log 2>&1
#
# 真因: deploy_production.sh の down --remove-orphans が staging-new を道連れ削除していた
# 根本修正: deploy_production.sh から --remove-orphans を除去 (fix/staging-orphan-protection-20260520)
# 本スクリプト: defense-in-depth として staging 停止時に自動 up -d する
#
# 2026-05-21 追加: Slack flood 抑制 (COOLDOWN)。staging が継続的に down かつ復旧が定着しない場合、
# 従来は 5 分毎に「停止を検知」を Slack へ連発していた。COOLDOWN_SEC 内は復旧は試みるが
# 通知は抑制し、復旧 or cooldown 経過時のみ通知する。
# 2026-05-22 根本修正: --no-build + image存在ガード + flock 多重実行防止 (OOM螺旋 incident 対応)

set -uo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/ultra-autotrade}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"
ENV_FILE="${ENV_FILE:-.env.staging-new}"
SENTINEL_CONTAINER="${SENTINEL_CONTAINER:-ultra-autotrade-postgres-staging-new}"
WEBHOOK_FILE="${WEBHOOK_FILE:-${COMPOSE_DIR}/.env.production}"
COOLDOWN_SEC="${COOLDOWN_SEC:-1800}"  # 30分: down 継続時の通知連発抑制
STATE_FILE="${STATE_FILE:-${TMPDIR:-/tmp}/.staging_watchdog_alert}"
LOG_PREFIX="[staging-watchdog] $(date '+%Y-%m-%dT%H:%M:%S')"

# 多重実行ガード: 前回の復旧/build が走行中に重ねて起動しない (OOM螺旋の遮断)
exec 9>"${TMPDIR:-/tmp}/.staging_watchdog.lock"
flock -n 9 || { echo "${LOG_PREFIX} 別 watchdog 実行中 — skip"; exit 0; }

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

# ---- 正常時: 直前に alert を出していたら復旧通知して state クリア ----
if is_staging_alive; then
  if [[ -f "${STATE_FILE}" ]]; then
    echo "${LOG_PREFIX} RECOVERED: staging stack restored (alert state クリア)"
    notify_slack "✅ [staging-watchdog] staging stack 復旧確認 (${SENTINEL_CONTAINER} running)。"
    rm -f "${STATE_FILE}" 2>/dev/null || true
  else
    echo "${LOG_PREFIX} staging healthy (${SENTINEL_CONTAINER} running)"
  fi
  exit 0
fi

# ---- 異常時: cooldown 判定 (通知抑制。復旧自体は毎回試みる) ----
now=$(date +%s)
should_notify=1
if [[ -f "${STATE_FILE}" ]]; then
  last=$(cat "${STATE_FILE}" 2>/dev/null || echo "0")
  if (( now - last < COOLDOWN_SEC )); then
    should_notify=0
  fi
fi

echo "${LOG_PREFIX} WARN: staging stack down — starting auto-recovery (notify=${should_notify})"
if [[ "${should_notify}" == "1" ]]; then
  notify_slack "⚠️ [staging-watchdog] staging stack 停止を検知。自動復旧を開始します。(以後 ${COOLDOWN_SEC}s は通知抑制)"
  echo "${now}" > "${STATE_FILE}" 2>/dev/null || true
fi

cd "${COMPOSE_DIR}" || { echo "${LOG_PREFIX} ERROR: cd ${COMPOSE_DIR} 失敗"; exit 1; }

# 根本修正: 必須 image が欠落していたら build せず alert して退避 (OOM螺旋の遮断)。
# watchdog は「既存 image の再起動」だけを行い、決して build しない。
missing=""
for img in $(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" config --images 2>/dev/null); do
  docker image inspect "$img" >/dev/null 2>&1 || missing="${missing} ${img}"
done
if [[ -n "${missing}" ]]; then
  echo "${LOG_PREFIX} ABORT: 必須 image 欠落 →${missing}. build は誘発せず手動対応待ち。"
  # image 欠落は自動復旧不可なので cooldown に関わらず毎回通知する
  notify_slack "❌ [staging-watchdog] image 欠落で自動復旧を中止(build抑止):${missing}。手動で deploy_staging.sh を実行してください。"
  exit 1
fi

# 根本修正: watchdog は決して build しない (--no-build)。image 欠落は上で弾く。
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-build 2>&1 || true

# 15秒待って確認
sleep 15

if is_staging_alive; then
  echo "${LOG_PREFIX} RECOVERED: staging stack restored"
  notify_slack "✅ [staging-watchdog] staging stack 自動復旧完了。"
  rm -f "${STATE_FILE}" 2>/dev/null || true
else
  echo "${LOG_PREFIX} ERROR: staging stack recovery FAILED"
  # 復旧失敗通知も should_notify のときのみ (連発防止)。
  if [[ "${should_notify}" == "1" ]]; then
    notify_slack "❌ [staging-watchdog] staging stack 自動復旧失敗。手動対応が必要です。(以後 ${COOLDOWN_SEC}s は通知抑制 — 継続 down 中)"
  fi
  exit 1
fi
