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
BACKEND_CONTAINER="ultra-autotrade-backend-staging"
POSTGRES_CONTAINER="ultra-autotrade-postgres-staging"
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
# スケジューラー健全性チェック（警告のみ、デプロイは止めない）
# ───────────────────────────────────────────────
if ! "${FRONTEND_ONLY}"; then
  log "15秒待機してスケジューラー状態を確認中..."
  sleep 15
  HEALTH_JSON=$(curl -sf --max-time 5 "http://localhost:8000/health" 2>/dev/null || echo '{}')
  SCHED_HEALTHY=$(echo "${HEALTH_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_healthy','unknown'))" 2>/dev/null || echo "unknown")
  if [ "${SCHED_HEALTHY}" = "False" ] || [ "${SCHED_HEALTHY}" = "false" ]; then
    log "⚠️  WARNING: scheduler_healthy=false — スケジューラーが overdue 状態です"
    log "   詳細: ${HEALTH_JSON}"
  elif [ "${SCHED_HEALTHY}" = "unknown" ]; then
    log "⚠️  WARNING: /health からスケジューラー状態を取得できませんでした"
  else
    log "scheduler_healthy=${SCHED_HEALTHY} ✓"
  fi
fi

# ───────────────────────────────────────────────
# デプロイ後 追加検証（WARNING のみ / デプロイは止めない）
# ───────────────────────────────────────────────

# 検証 1: Mixed Content 検出
check_mixed_content() {
  log "=== Mixed Content チェック ==="
  local http_count
  http_count=$(docker exec "${FRONTEND_CONTAINER}" \
    grep -r "http://77\|http://localhost:8000" /app/.next/static/chunks/ 2>/dev/null \
    | wc -l || echo "0")
  if [ "${http_count}" -gt 0 ]; then
    log "⚠️  WARNING: フロントエンドバンドルに http:// URL が ${http_count} 件残っています"
    log "   → NEXT_PUBLIC_* 環境変数が docker-compose build.args に反映されていない可能性"
    log "   → docker compose build --no-cache frontend を実行してください"
  else
    log "✅ Mixed Content なし"
  fi
}

# 検証 2: Cloudflare Tunnel 確認
check_tunnel() {
  log "=== Cloudflare Tunnel チェック ==="
  local named_tunnel
  named_tunnel=$(pgrep -f "cloudflared.*tunnel.*run" 2>/dev/null | wc -l || echo "0")
  if [ "${named_tunnel}" -ge 1 ]; then
    log "✅ Named Tunnel 稼働中 (${named_tunnel} プロセス)"
  else
    # docker コンテナ内の cloudflared を確認
    local container_running
    container_running=$(docker inspect --format='{{.State.Running}}' \
      "ultra-autotrade-cloudflared-staging" 2>/dev/null || echo "false")
    if [ "${container_running}" = "true" ]; then
      log "✅ cloudflared コンテナ稼働中"
    else
      log "⚠️  WARNING: Cloudflare Tunnel が検出されませんでした"
      log "   → フロントエンド(:3000) + バックエンド(:8000) 両方のトンネルが必要"
      log "   → docker compose logs ultra-autotrade-cloudflared-staging で確認してください"
    fi
  fi
}

# 検証 3: DB カラム drift 検出
check_db_drift() {
  log "=== DB カラム drift チェック ==="
  local db_columns
  db_columns=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
    "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='users';" \
    2>/dev/null | tr -d ' \n' || echo "")
  if [ -z "${db_columns}" ]; then
    log "⚠️  WARNING: DB から users テーブルのカラムを取得できませんでした"
    return
  fi
  log "  DB users columns: ${db_columns}"
  local model_columns
  model_columns=$(docker exec "${BACKEND_CONTAINER}" python -c \
    "from app.auth.models import User; cols=[c.key for c in User.__table__.columns]; print(','.join(sorted(cols)))" \
    2>/dev/null || echo "")
  if [ -z "${model_columns}" ]; then
    log "⚠️  WARNING: モデルからカラムを取得できませんでした"
    return
  fi
  log "  Model columns: ${model_columns}"
  local diff
  diff=$(comm -23 \
    <(echo "${model_columns}" | tr ',' '\n' | sort) \
    <(echo "${db_columns}" | tr ',' '\n' | sort) || true)
  if [ -n "${diff}" ]; then
    log "⚠️  WARNING: 以下のカラムがモデルにあるが DB にありません:"
    log "   ${diff}"
    log "   → ALTER TABLE users ADD COLUMN IF NOT EXISTS ... で追加してください"
  else
    log "✅ DB カラム drift なし"
  fi
}

# 検証 4: 401 エラー確認（INTERNAL_API_TOKEN 問題検出）
check_auth_errors() {
  log "=== 内部 API 認証エラーチェック ==="
  local auth_errors
  auth_errors=$(docker logs "${BACKEND_CONTAINER}" 2>&1 | tail -100 \
    | grep -c "401 Unauthorized" || echo "0")
  if [ "${auth_errors}" -gt 5 ]; then
    log "⚠️  WARNING: 直近100行に 401 Unauthorized が ${auth_errors} 件"
    log "   → INTERNAL_API_TOKEN が .env.staging に設定されているか確認してください"
  else
    log "✅ 401 エラー ${auth_errors} 件（正常範囲）"
  fi
}

# 検証 5: CORS preflight 自動検証
check_cors() {
  log "=== CORS preflight チェック ==="
  local frontend_origin="https://app.ultra-auto-trade.com"
  local cors_header
  cors_header=$(curl -s -I \
    -H "Origin: ${frontend_origin}" \
    -H "Access-Control-Request-Method: GET" \
    --max-time 5 \
    http://localhost:8000/health 2>/dev/null \
    | grep -i "access-control-allow-origin" | tr -d '\r' || echo "")
  if echo "${cors_header}" | grep -q "${frontend_origin}\|\*"; then
    log "✅ CORS: ${frontend_origin} が許可されています"
  else
    log "⚠️  WARNING: CORS ヘッダーに ${frontend_origin} が含まれていません"
    log "   → .env.staging の CORS_ORIGINS に ${frontend_origin} を追加してください"
    log "   → レスポンス: ${cors_header:-（ヘッダーなし）}"
  fi
}

# 全追加検証を実行（各ステップは独立して動作）
run_post_deploy_checks() {
  log "=== デプロイ後追加検証 開始 ==="
  check_mixed_content || true
  check_tunnel        || true
  check_db_drift      || true
  check_auth_errors   || true
  check_cors          || true
  log "=== デプロイ後追加検証 完了 ==="
}

if ! "${BACKEND_ONLY}"; then
  run_post_deploy_checks
fi

# ───────────────────────────────────────────────
# 完了報告
# ───────────────────────────────────────────────
log "コンテナ状態:"
${DC} -f "${COMPOSE_FILE}" ps

slack_notify "✅ [deploy_staging.sh] デプロイ成功\n環境: staging\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "デプロイ完了"
