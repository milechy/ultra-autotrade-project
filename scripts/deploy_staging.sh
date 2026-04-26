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

# Ultra AutoTrade – staging ワンショットデプロイスクリプト（真のStaging用）
# (2026-04-17 B案リネーム: 新規作成)
#
# 対象環境: staging.ultra-auto-trade.com / api-staging.ultra-auto-trade.com
# Shadow Mode専用 (AI_SHADOW_MODE=true / REBALANCE_SHADOW_MODE=true)
# ポート: frontend 3001 / backend 8001 / postgres 5433
#
# 使い方:
#   ./scripts/deploy_staging.sh                  # フルデプロイ
#   ./scripts/deploy_staging.sh --frontend-only  # フロントエンドのみ
#   ./scripts/deploy_staging.sh --backend-only   # バックエンドのみ
#   ./scripts/deploy_staging.sh --no-build       # ビルドなし（up -d のみ）
#   ./scripts/deploy_staging.sh --help

# ───────────────────────────────────────────────
# 定数
# ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="docker-compose.staging.yml"
ENV_FILE=".env.staging-new"
FRONTEND_CONTAINER="ultra-autotrade-frontend-staging-new"
BACKEND_CONTAINER="ultra-autotrade-backend-staging-new"
POSTGRES_CONTAINER="ultra-autotrade-postgres-staging-new"
HEALTH_TIMEOUT=60
# Shadow Mode強制確認
REQUIRED_SHADOW_MODE="true"

# ───────────────────────────────────────────────
# ヘルパー
# ───────────────────────────────────────────────
log()  { echo "[deploy-staging] $*"; }
err()  { echo "[deploy-staging] ERROR: $*" >&2; }

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
deploy_staging.sh — Ultra AutoTrade staging デプロイ（真のStaging用）

使い方:
  ./scripts/deploy_staging.sh [OPTIONS]

オプション:
  --frontend-only   フロントエンドのみリビルド＆再起動
  --backend-only    バックエンドのみリビルド＆再起動
  --no-build        ビルドなしで up -d のみ実行
  --help            このヘルプを表示

注意:
  - /opt/ultra-autotrade（または git root）から実行すること
  - .env.staging が同ディレクトリに存在していること
  - Shadow Mode (AI_SHADOW_MODE=true) が必須
  - port 3001/8001/5433 を使用（productionの 3000/8000/5432 とは別）
EOF
  exit 0
}

# docker compose / docker-compose の解決
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

# env_file 適用検証: backend ランタイムの DATABASE_URL PW が env_file の値と一致するか確認
verify_env_file_applied() {
  local container="${BACKEND_CONTAINER}"
  local env_file="${ENV_FILE}"
  log "=== env_file 適用検証 ==="
  local expected_pw
  expected_pw=$(grep "^POSTGRES_PASSWORD=" "${env_file}" | cut -d= -f2- | tr -d '\n')
  if [[ -z "${expected_pw}" ]]; then
    expected_pw=$(grep "^DATABASE_URL=" "${env_file}" | grep -oP '(?<=://[^:]+:)[^@]+' | head -1)
  fi
  local expected_md5
  expected_md5=$(echo -n "${expected_pw}" | md5sum | awk '{print $1}')

  local runtime_md5
  runtime_md5=$(docker exec "${container}" env 2>/dev/null | grep "^DATABASE_URL=" | grep -oP '(?<=://[^:]+:)[^@]+' | tr -d '\n' | md5sum | awk '{print $1}')

  if [[ "${expected_md5}" == "${runtime_md5}" ]]; then
    log "✅ DATABASE_URL PW md5 一致: ${runtime_md5}"
  else
    err "❌ DATABASE_URL PW md5 不一致!"
    err "   expected (from ${env_file}): ${expected_md5}"
    err "   runtime  (container env):   ${runtime_md5}"
    err "   --env-file が正しく渡されていない可能性があります"
    return 1
  fi
}

# ヘルスチェック待ちループ
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
  err "${ENV_FILE} が見つかりません — デプロイを中止します"
  exit 1
fi

# Shadow Mode チェック（staging必須）
SHADOW_CHECK=$(grep "^AI_SHADOW_MODE=" "${ENV_FILE}" | cut -d= -f2 | tr -d '"' | tr -d "'" || echo "")
if [[ "${SHADOW_CHECK}" != "true" ]]; then
  err "AI_SHADOW_MODE=true が .env.staging に設定されていません。"
  err "Staging環境ではShadow Modeが必須です。デプロイを中止します。"
  exit 1
fi
log "✅ Shadow Mode確認: AI_SHADOW_MODE=${SHADOW_CHECK}"

DC=$(resolve_dc)
log "docker compose コマンド: ${DC}"

# ───────────────────────────────────────────────
# 共通ステップ
# ───────────────────────────────────────────────
log "git pull origin dev"
git pull origin dev

log ".env.staging を読み込み（ビルド ARG 用）"
# shellcheck disable=SC2046
export $(grep -v '^#' "${ENV_FILE}" | grep '=' | xargs)

# ───────────────────────────────────────────────
# モード別デプロイ
# ───────────────────────────────────────────────
on_failure() {
  err "デプロイ失敗。コンテナログ末尾:"
  ${DC} -f "${COMPOSE_FILE}" logs --tail=20 2>/dev/null || true
  slack_notify "❌ [deploy_staging.sh] Stagingデプロイ失敗\n原因: ヘルスチェックタイムアウトまたはビルドエラー"
  exit 1
}
trap on_failure ERR

if "${FRONTEND_ONLY}"; then
  log "フロントエンドのみデプロイ"

  ${DC} -f "${COMPOSE_FILE}" stop frontend
  docker rm -f "${FRONTEND_CONTAINER}" 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "古いフロントエンドイメージを完全削除..."
    docker images --format "{{.Repository}} {{.ID}}" \
      | grep -E "frontend.*staging-new|ultra-autotrade-staging.*front" \
      | awk '{print $2}' \
      | xargs -r docker rmi -f 2>/dev/null || true

    log "frontend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d frontend

  wait_healthy "http://localhost:3001" "frontend(staging)" || on_failure

elif "${BACKEND_ONLY}"; then
  log "バックエンドのみデプロイ"

  ${DC} -f "${COMPOSE_FILE}" stop backend

  if ! "${NO_BUILD}"; then
    log "backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d backend

  wait_healthy "http://localhost:8001/health" "backend(staging)" || on_failure
  verify_env_file_applied || on_failure

else
  log "フルデプロイ開始（Staging環境）"

  log "孤立コンテナを含めて停止・削除"
  ${DC} -f "${COMPOSE_FILE}" down --remove-orphans

  # staging-new コンテナのみ強制削除
  docker rm -f $(docker ps -aq --filter "name=ultra-autotrade.*staging-new") 2>/dev/null || true

  log "未使用ボリュームを削除（DBボリュームは名前付きのため保護される）..."
  docker volume prune -f 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "古いフロントエンドイメージを完全削除..."
    docker images --format "{{.Repository}} {{.ID}}" \
      | grep -E "frontend.*staging-new|ultra-autotrade-staging.*front" \
      | awk '{print $2}' \
      | xargs -r docker rmi -f 2>/dev/null || true

    log "frontend / backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  log "全サービスを起動（port 3001/8001/5433）"
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

  wait_healthy "http://localhost:8001/health" "backend(staging)"  || on_failure
  wait_healthy "http://localhost:3001"         "frontend(staging)" || on_failure
  verify_env_file_applied || on_failure
fi

# ───────────────────────────────────────────────
# Shadow Mode確認（デプロイ後）
# ───────────────────────────────────────────────
if ! "${FRONTEND_ONLY}"; then
  log "Shadow Mode最終確認..."
  HEALTH_JSON=$(curl -sf --max-time 5 "http://localhost:8001/health" 2>/dev/null || echo '{}')
  log "health: ${HEALTH_JSON}"
fi

# ───────────────────────────────────────────────
# 最終ヘルスチェック
# ───────────────────────────────────────────────
log "=== 最終ヘルスチェック ==="

if ! "${FRONTEND_ONLY}"; then
  BE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8001/health 2>/dev/null || echo "000")
  if [ "${BE_STATUS}" = "200" ]; then
    log "✅ backend  http://localhost:8001/health → ${BE_STATUS}"
  else
    log "⚠️  WARNING: backend  http://localhost:8001/health → ${BE_STATUS}"
  fi
fi

if ! "${BACKEND_ONLY}"; then
  FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:3001 2>/dev/null || echo "000")
  if [ "${FE_STATUS}" = "200" ]; then
    log "✅ frontend http://localhost:3001 → ${FE_STATUS}"
  else
    log "⚠️  WARNING: frontend http://localhost:3001 → ${FE_STATUS}"
  fi
fi

log "=== 最終ヘルスチェック 完了 ==="

log "コンテナ状態:"
${DC} -f "${COMPOSE_FILE}" ps

slack_notify "✅ [deploy_staging.sh] Stagingデプロイ成功\n環境: staging (Shadow Mode)\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "Stagingデプロイ完了"
