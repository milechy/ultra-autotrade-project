#!/bin/bash
set -euo pipefail

# ───────────────────────────────────────────────
# -v / --volumes フラグ誤使用防止ガード
# ───────────────────────────────────────────────
for _arg in "$@"; do
  if [[ "$_arg" == "-v" || "$_arg" == "--volumes" ]]; then
    echo "❌ ERROR: -v / --volumes フラグは禁止です。DBボリュームが削除されます。"
    echo "   down のみ使用してください: docker compose ... down"
    exit 1
  fi
done

# Ultra AutoTrade – v4 staging ワンショットデプロイスクリプト
# (2026-06-16 新設 / Asana 1215740593437797)
#
# 対象環境: staging-v4.ultra-auto-trade.com / api-staging-v4.ultra-auto-trade.com
# 【軽量構成 = 4 サービス / single backend】
#   v3 staging (deploy_staging.sh) と異なり blue/green を持たない。再デプロイ時の
#   数秒のダウンを許容する (v4 staging は zero-downtime 不要)。
# Shadow Mode専用 (AI_SHADOW_MODE=true / REBALANCE_SHADOW_MODE=true)
# ポート: frontend 127.0.0.1:3002 / nginx 127.0.0.1:8083 / backend 127.0.0.1:8030 / postgres 127.0.0.1:5434
#
# 使い方:
#   ./scripts/deploy_staging_v4.sh                  # フルデプロイ
#   ./scripts/deploy_staging_v4.sh --frontend-only  # フロントエンドのみ
#   ./scripts/deploy_staging_v4.sh --backend-only   # バックエンドのみ再ビルド＆再起動
#   ./scripts/deploy_staging_v4.sh --no-build       # ビルドなし（up -d のみ）
#   ./scripts/deploy_staging_v4.sh --help

# ───────────────────────────────────────────────
# 定数
# ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="docker-compose.staging-v4.yml"
ENV_FILE=".env.staging-v4"
FRONTEND_CONTAINER="ultra-autotrade-frontend-staging-v4"
BACKEND_CONTAINER="ultra-autotrade-backend-staging-v4"
NGINX_CONTAINER="ultra-autotrade-nginx-staging-v4"
POSTGRES_CONTAINER="ultra-autotrade-postgres-staging-v4"
HEALTH_TIMEOUT=60

BACKEND_PORT=8030
NGINX_PORT=8083
FRONTEND_PORT=3002

LOCK_FILE="${PROJECT_ROOT}/.deploy-staging-v4.lock"
LOG_FILE="${PROJECT_ROOT}/logs/deploy_staging_v4.log"

# ───────────────────────────────────────────────
# ヘルパー
# ───────────────────────────────────────────────
mkdir -p "$(dirname "${LOG_FILE}")"
log()  { echo "[deploy-staging-v4] $*" | tee -a "${LOG_FILE}"; }
err()  { echo "[deploy-staging-v4] ERROR: $*" | tee -a "${LOG_FILE}" >&2; }

slack_notify() {
  local msg="$1"
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -s -X POST "${SLACK_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${msg}\"}" >/dev/null || true
  fi
}

show_help() {
  cat <<'EOF'
deploy_staging_v4.sh — Ultra AutoTrade v4 staging デプロイ（軽量 single backend 構成）

使い方:
  ./scripts/deploy_staging_v4.sh [OPTIONS]

オプション:
  --frontend-only   フロントエンドのみリビルド＆再起動
  --backend-only    バックエンドのみリビルド＆再起動（数秒のダウンあり）
  --no-build        ビルドなしで up -d のみ実行
  --help            このヘルプを表示

注意:
  - git root から実行すること
  - .env.staging-v4 が同ディレクトリに存在していること（テンプレート: .env.staging-v4.example）
  - Shadow Mode (AI_SHADOW_MODE=true) が必須
  - ポート: frontend 3002 / nginx 8083 / backend 8030 / postgres 5434
EOF
  exit 0
}

resolve_dc() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    err "docker compose または docker-compose が見つかりません"
    exit 1
  fi
}

wait_healthy() {
  local url="$1"
  local label="$2"
  local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))

  log "ヘルスチェック待ち: ${label} (最大 ${HEALTH_TIMEOUT}s)"
  while true; do
    if curl -sf --max-time 3 "${url}" >/dev/null 2>&1; then
      log "${label} OK"
      return 0
    fi
    if [[ $(date +%s) -ge ${deadline} ]]; then
      err "${label} がタイムアウトしました (${url})"
      return 1
    fi
    sleep 3
  done
}

# ───────────────────────────────────────────────
# 引数パース
# ───────────────────────────────────────────────
FRONTEND_ONLY=false
BACKEND_ONLY=false
NO_BUILD=false

for arg in "$@"; do
  case "${arg}" in
    --frontend-only) FRONTEND_ONLY=true ;;
    --backend-only)  BACKEND_ONLY=true ;;
    --no-build)      NO_BUILD=true ;;
    --help)          show_help ;;
    *) err "不明なオプション: ${arg}"; exit 1 ;;
  esac
done

# ───────────────────────────────────────────────
# 前提チェック
# ───────────────────────────────────────────────
cd "${PROJECT_ROOT}"
log "project root: ${PROJECT_ROOT}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  err "${COMPOSE_FILE} が見つかりません（${PROJECT_ROOT}）"
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  err "${ENV_FILE} が見つかりません — デプロイを中止します（テンプレート: ${ENV_FILE}.example）"
  exit 1
fi

# === デプロイの同時実行排除 (flock) ===
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
  err "別のデプロイが進行中です: ${LOCK_FILE}"
  exit 1
fi

# Shadow Mode チェック（staging必須）
SHADOW_CHECK=$(grep "^AI_SHADOW_MODE=" "${ENV_FILE}" | cut -d= -f2 | tr -d '"' | tr -d "'" || echo "")
if [[ "${SHADOW_CHECK}" != "true" ]]; then
  err "AI_SHADOW_MODE=true が ${ENV_FILE} に設定されていません。"
  err "Staging環境ではShadow Modeが必須です。デプロイを中止します。"
  exit 1
fi
log "✅ Shadow Mode確認: AI_SHADOW_MODE=${SHADOW_CHECK}"

DC=$(resolve_dc)
log "docker compose コマンド: ${DC}"

# ───────────────────────────────────────────────
# 共通ステップ
# ───────────────────────────────────────────────
log "git pull origin main"
git pull origin main

log "${ENV_FILE} を読み込み（ビルド ARG 用）"
# shellcheck disable=SC2046
export $(grep -v '^#' "${ENV_FILE}" | grep '=' | xargs)

# デプロイ版識別子: PostHog の app_version に git short SHA を埋め込む。
export NEXT_PUBLIC_APP_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
log "NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION} を frontend build ARG に埋め込み"

# ───────────────────────────────────────────────
# 失敗時ハンドラ
# ───────────────────────────────────────────────
on_failure() {
  err "デプロイ失敗。コンテナログ末尾:"
  ${DC} -f "${COMPOSE_FILE}" logs --tail=20 2>/dev/null || true
  slack_notify "❌ [deploy_staging_v4.sh] v4 Stagingデプロイ失敗\n原因: ヘルスチェックタイムアウトまたはビルドエラー"
  exit 1
}
trap on_failure ERR

# ───────────────────────────────────────────────
# モード別デプロイ
# ───────────────────────────────────────────────
if "${FRONTEND_ONLY}"; then
  log "フロントエンドのみデプロイ (v4 staging)"

  ${DC} -f "${COMPOSE_FILE}" stop frontend
  docker rm -f "${FRONTEND_CONTAINER}" 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "frontend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
    up -d --no-deps --force-recreate frontend

  wait_healthy "http://127.0.0.1:${FRONTEND_PORT}" "frontend(staging-v4)" || on_failure

elif "${BACKEND_ONLY}"; then
  log "バックエンドのみデプロイ (v4 staging / 数秒のダウンあり)"

  if ! "${NO_BUILD}"; then
    log "backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
    up -d --no-deps --force-recreate backend

  wait_healthy "http://127.0.0.1:${BACKEND_PORT}/health"  "backend (direct)" || on_failure
  wait_healthy "http://127.0.0.1:${NGINX_PORT}/health"    "nginx → backend"  || on_failure

else
  log "フルデプロイ開始（v4 Staging環境 / 4 サービス軽量構成）"

  log "孤立コンテナを含めて停止・削除"
  ${DC} -f "${COMPOSE_FILE}" down --remove-orphans

  # staging-v4 コンテナのみ強制削除
  docker rm -f $(docker ps -aq --filter "name=ultra-autotrade.*staging-v4") 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "frontend / backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  log "全サービスを起動 (postgres → backend → nginx → frontend)"
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

  wait_healthy "http://127.0.0.1:${BACKEND_PORT}/health"  "backend (direct)" || on_failure
  wait_healthy "http://127.0.0.1:${NGINX_PORT}/health"    "nginx → backend"  || on_failure
  wait_healthy "http://127.0.0.1:${FRONTEND_PORT}"        "frontend(staging-v4)" || on_failure
fi

# ───────────────────────────────────────────────
# Shadow Mode確認（デプロイ後）
# ───────────────────────────────────────────────
if ! "${FRONTEND_ONLY}"; then
  log "Shadow Mode最終確認 + スケジューラー状態チェック..."
  HEALTH_JSON=$(curl -sf --max-time 5 "http://127.0.0.1:${NGINX_PORT}/health" 2>/dev/null || echo '{}')
  log "health: ${HEALTH_JSON}"

  SCHED_HEALTHY=$(echo "${HEALTH_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_healthy','unknown'))" 2>/dev/null || echo "unknown")
  if [ "${SCHED_HEALTHY}" = "False" ] || [ "${SCHED_HEALTHY}" = "false" ]; then
    log "⚠️  WARNING: scheduler_healthy=false — スケジューラーが overdue 状態です"
  elif [ "${SCHED_HEALTHY}" = "unknown" ]; then
    log "⚠️  WARNING: /health からスケジューラー状態を取得できませんでした"
  else
    log "scheduler_healthy=${SCHED_HEALTHY} ✓"
  fi

  SCHED_LAST_ERROR=$(echo "${HEALTH_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_last_error') or '')" 2>/dev/null || echo "")
  if [ -n "${SCHED_LAST_ERROR}" ]; then
    log "⚠️  WARNING: scheduler_last_error 検出: ${SCHED_LAST_ERROR}"
  else
    log "scheduler_last_error=なし ✓"
  fi
fi

# ───────────────────────────────────────────────
# 最終ヘルスチェック
# ───────────────────────────────────────────────
log "=== 最終ヘルスチェック ==="

if ! "${FRONTEND_ONLY}"; then
  BE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${NGINX_PORT}/health" 2>/dev/null || echo "000")
  if [ "${BE_STATUS}" = "200" ]; then
    log "✅ backend  http://127.0.0.1:${NGINX_PORT}/health → ${BE_STATUS}"
  else
    log "⚠️  WARNING: backend  http://127.0.0.1:${NGINX_PORT}/health → ${BE_STATUS}"
  fi
fi

if ! "${BACKEND_ONLY}"; then
  FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${FRONTEND_PORT}" 2>/dev/null || echo "000")
  if [ "${FE_STATUS}" = "200" ]; then
    log "✅ frontend http://127.0.0.1:${FRONTEND_PORT} → ${FE_STATUS}"
  else
    log "⚠️  WARNING: frontend http://127.0.0.1:${FRONTEND_PORT} → ${FE_STATUS}"
  fi
fi

log "=== 最終ヘルスチェック 完了 ==="

log "コンテナ状態:"
${DC} -f "${COMPOSE_FILE}" ps

slack_notify "✅ [deploy_staging_v4.sh] v4 Stagingデプロイ成功\n環境: staging-v4 (Shadow Mode / single backend)\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "v4 Stagingデプロイ完了"
