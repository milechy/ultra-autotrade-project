#!/bin/bash
set -euo pipefail

# Ultra AutoTrade – staging ワンショットデプロイスクリプト
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
ENV_FILE=".env.staging"
FRONTEND_CONTAINER="ultra-autotrade-frontend-staging"
HEALTH_TIMEOUT=60

# ───────────────────────────────────────────────
# ヘルパー
# ───────────────────────────────────────────────
log()  { echo "[deploy] $*"; }
err()  { echo "[deploy] ERROR: $*" >&2; }

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
deploy_staging.sh — Ultra AutoTrade staging デプロイ

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

DC=$(resolve_dc)
log "docker compose コマンド: ${DC}"

# ───────────────────────────────────────────────
# 共通ステップ 1-4
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
  slack_notify "❌ [deploy_staging.sh] デプロイ失敗\n原因: ヘルスチェックタイムアウトまたはビルドエラー"
  exit 1
}
trap on_failure ERR

if "${FRONTEND_ONLY}"; then
  # ─── フロントエンドのみ ───────────────────────
  log "フロントエンドのみデプロイ"

  ${DC} -f "${COMPOSE_FILE}" stop frontend
  docker rm -f "${FRONTEND_CONTAINER}" 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "frontend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d frontend

  wait_healthy "http://localhost:3000" "frontend" || on_failure

elif "${BACKEND_ONLY}"; then
  # ─── バックエンドのみ ─────────────────────────
  log "バックエンドのみデプロイ"

  ${DC} -f "${COMPOSE_FILE}" stop backend

  if ! "${NO_BUILD}"; then
    log "backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache backend
  fi

  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d backend

  wait_healthy "http://localhost:8000/health" "backend" || on_failure

else
  # ─── フルデプロイ ──────────────────────────────
  log "フルデプロイ開始"

  log "孤立コンテナを含めて停止・削除"
  ${DC} -f "${COMPOSE_FILE}" down --remove-orphans

  # docker rm -f で残留コンテナを強制削除
  # shellcheck disable=SC2046
  docker rm -f $(docker ps -aq --filter "name=ultra-autotrade") 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "frontend / backend をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend backend
  fi

  log "全サービスを起動"
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

  wait_healthy "http://localhost:8000/health" "backend"  || on_failure
  wait_healthy "http://localhost:3000"         "frontend" || on_failure
fi

# ───────────────────────────────────────────────
# 完了報告
# ───────────────────────────────────────────────
log "コンテナ状態:"
${DC} -f "${COMPOSE_FILE}" ps

slack_notify "✅ [deploy_staging.sh] デプロイ成功\n環境: staging\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "デプロイ完了"
