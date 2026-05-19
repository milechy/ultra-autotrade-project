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
# (2026-04-27 ゼロダウンタイム対応: --backend-only は Blue/Green 切替に変更)
#
# 対象環境: staging.ultra-auto-trade.com / api-staging.ultra-auto-trade.com
# Shadow Mode専用 (AI_SHADOW_MODE=true / REBALANCE_SHADOW_MODE=true)
# ポート: frontend 127.0.0.1:3001 / nginx 127.0.0.1:8082
#        backend-blue 127.0.0.1:8020 / backend-green 127.0.0.1:8021 / postgres 127.0.0.1:5433
#
# 使い方:
#   ./scripts/deploy_staging.sh                  # フルデプロイ (初期 active=blue)
#   ./scripts/deploy_staging.sh --frontend-only  # フロントエンドのみ
#   ./scripts/deploy_staging.sh --backend-only   # Blue/Green 切替 (ゼロダウンタイム)
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
BACKEND_BLUE_CONTAINER="ultra-autotrade-backend-blue-staging-new"
BACKEND_GREEN_CONTAINER="ultra-autotrade-backend-green-staging-new"
NGINX_CONTAINER="ultra-autotrade-nginx-staging-new"
POSTGRES_CONTAINER="ultra-autotrade-postgres-staging-new"
HEALTH_TIMEOUT=60
REQUIRED_SHADOW_MODE="true"

# Blue/Green host-side ports (compose の定義と一致させること)
BLUE_PORT=8020
GREEN_PORT=8021
NGINX_PORT=8082
FRONTEND_PORT=3001

UPSTREAM_CONF="${PROJECT_ROOT}/docker/nginx/upstream.staging.conf"
LOCK_FILE="${PROJECT_ROOT}/.deploy-staging.lock"

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
  --backend-only    Blue/Green 切替によるゼロダウンタイムデプロイ
  --no-build        ビルドなしで up -d のみ実行
  --help            このヘルプを表示

注意:
  - /opt/ultra-autotrade（または git root）から実行すること
  - .env.staging-new が同ディレクトリに存在していること
  - Shadow Mode (AI_SHADOW_MODE=true) が必須
  - ポート: frontend 3001 / nginx 8082 / backend-blue 8020 / backend-green 8021 / postgres 5433
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
# Blue/Green ヘルパー
# ───────────────────────────────────────────────

read_active_slot() {
  if [[ ! -f "${UPSTREAM_CONF}" ]]; then
    echo "unknown"
    return
  fi
  # 新形式 (2026-05-12 以降): set $backend backend-blue:8000;
  # 旧形式 (互換): server backend-blue:8000 max_fails=...;
  if grep -qE '^[[:space:]]*set[[:space:]]+\$backend[[:space:]]+backend-blue:' "${UPSTREAM_CONF}" \
     || grep -qE '^[[:space:]]*server[[:space:]]+backend-blue:' "${UPSTREAM_CONF}"; then
    echo "blue"
  elif grep -qE '^[[:space:]]*set[[:space:]]+\$backend[[:space:]]+backend-green:' "${UPSTREAM_CONF}" \
       || grep -qE '^[[:space:]]*server[[:space:]]+backend-green:' "${UPSTREAM_CONF}"; then
    echo "green"
  else
    echo "unknown"
  fi
}

# upstream.staging.conf を書き換え (awk + cat >、sed -i / mv は禁止)
# cat > で in-place 書き換えすることで inode を保持し bind-mount を維持する。
# nginx 未起動時は docker exec をスキップ (フルデプロイ・リカバリ時のフェイルセーフ)。
write_upstream_conf() {
  local new_slot="$1"
  local tmp_file
  tmp_file=$(mktemp "${UPSTREAM_CONF}.XXXXXX")
  # 2026-05-12 以降の新形式: nginx.conf の resolver + 変数 proxy_pass と対になる。
  # `set $backend backend-blue:8000;` を nginx の `location /` で include し、
  # `proxy_pass http://$backend;` に渡す。詳細は upstream.staging.conf ヘッダコメント参照。
  awk -v slot="${new_slot}" '
    BEGIN {
      printf "set $backend backend-%s:8000;\n", slot
    }
  ' </dev/null > "${tmp_file}"
  # cat > preserves inode (mv would break the bind-mount by replacing it)
  cat "${tmp_file}" > "${UPSTREAM_CONF}"
  rm -f "${tmp_file}"
  log "Host file updated: ${UPSTREAM_CONF} → backend-${new_slot}"

  # Sync into container only when nginx is running (skip during full deploy / recovery)
  if docker ps --filter "name=${NGINX_CONTAINER}" --filter "status=running" \
       --format "{{.Names}}" 2>/dev/null | grep -q "^${NGINX_CONTAINER}$"; then
    docker exec -i "${NGINX_CONTAINER}" sh -c 'cat > /etc/nginx/conf.d/upstream.conf' < "${UPSTREAM_CONF}"
    log "Container file synced: ${NGINX_CONTAINER}"
  else
    log "WARN: ${NGINX_CONTAINER} not running — skipping container sync (bind-mount will apply on next start)"
  fi
}

active_backend_container() {
  local slot
  slot=$(read_active_slot)
  if [[ "${slot}" = "green" ]]; then
    echo "${BACKEND_GREEN_CONTAINER}"
  else
    echo "${BACKEND_BLUE_CONTAINER}"
  fi
}

deploy_backend_zero_downtime() {
  local active_slot inactive_slot inactive_port
  active_slot=$(read_active_slot)

  if [[ "${active_slot}" = "blue" ]]; then
    inactive_slot="green"; inactive_port="${GREEN_PORT}"
  elif [[ "${active_slot}" = "green" ]]; then
    inactive_slot="blue";  inactive_port="${BLUE_PORT}"
  else
    err "upstream.conf から active slot を判定できません: ${UPSTREAM_CONF}"
    return 1
  fi

  log "Blue/Green 切替開始 (staging): active=${active_slot} → new=${inactive_slot}(:${inactive_port})"

  if ! "${NO_BUILD}"; then
    log "backend-${inactive_slot} をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build "backend-${inactive_slot}"
  fi

  log "backend-${inactive_slot} を起動..."
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps "backend-${inactive_slot}"

  if ! wait_healthy "http://127.0.0.1:${inactive_port}/health" "backend-${inactive_slot}"; then
    err "新コンテナのヘルスチェック失敗。切替を中止し新コンテナを停止します"
    ${DC} -f "${COMPOSE_FILE}" stop "backend-${inactive_slot}" 2>/dev/null || true
    return 1
  fi

  log "upstream.conf を ${inactive_slot} に書き換え..."
  write_upstream_conf "${inactive_slot}"

  log "nginx -s reload を実行..."
  if ! docker exec "${NGINX_CONTAINER}" nginx -s reload; then
    err "nginx reload 失敗。upstream.conf を ${active_slot} に戻して再 reload..."
    write_upstream_conf "${active_slot}"
    docker exec "${NGINX_CONTAINER}" nginx -s reload || true
    return 1
  fi
  log "✅ nginx upstream → backend-${inactive_slot} 切替完了"

  log "30秒待機して既存接続が収束するのを待つ..."
  sleep 30

  log "backend-${active_slot} を stop (緊急ロールバック用に rm はしない)..."
  ${DC} -f "${COMPOSE_FILE}" stop "backend-${active_slot}"

  log "✅ Blue/Green 切替完了 (staging): active=${inactive_slot}"
  return 0
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

if [[ ! -f "${UPSTREAM_CONF}" ]]; then
  err "${UPSTREAM_CONF} が見つかりません — Blue/Green 構成が壊れている可能性"
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
log "現在の active slot: $(read_active_slot)"

# ───────────────────────────────────────────────
# 共通ステップ
# ───────────────────────────────────────────────
log "git pull origin main"
git pull origin main

log "${ENV_FILE} を読み込み（ビルド ARG 用）"
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

  # CLAUDE.md「本番フロントエンド操作ルール」遵守 + 2026-05-12 RCA 対応:
  # --no-deps --force-recreate で他サービスへの波及を防ぐ。
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
    up -d --no-deps --force-recreate frontend

  wait_healthy "http://127.0.0.1:${FRONTEND_PORT}" "frontend(staging)" || on_failure

  # ─── post-deploy: nginx 経由 /health 疎通テスト ───
  # 内部ヘルスチェックだけでは nginx → backend 経路の障害 (upstream IP 固着) を検出できない。
  # staging は CF Access の認可ヘッダが curl 側で取れないケースがあるため、nginx 内部
  # `127.0.0.1:${NGINX_PORT}/health` を**安定して**通っているか 5 連続 200 で確認する。
  # 最大 30 回 (約 90s) で 5 連続 200 を達成できなければ nginx -s reload を試行。
  log "post-deploy: nginx 経由 /health で疎通を 5 連続 200 で確認..."
  STAGING_HEALTH_URL="http://127.0.0.1:${NGINX_PORT}/health"
  POST_DEPLOY_OK=false
  CONSECUTIVE_200=0
  POST_DEPLOY_CODE=""
  for i in $(seq 1 30); do
    POST_DEPLOY_CODE=$(curl -sf -o /dev/null -m 5 -w "%{http_code}" "${STAGING_HEALTH_URL}" || echo "000")
    if [[ "${POST_DEPLOY_CODE}" == "200" ]]; then
      CONSECUTIVE_200=$((CONSECUTIVE_200 + 1))
      log "  nginx /health [attempt ${i}] = 200 (consecutive ${CONSECUTIVE_200}/5)"
      if [[ "${CONSECUTIVE_200}" -ge 5 ]]; then
        POST_DEPLOY_OK=true
        break
      fi
    else
      log "  nginx /health [attempt ${i}] = ${POST_DEPLOY_CODE} (consecutive reset 0/5)"
      CONSECUTIVE_200=0
    fi
    sleep 3
  done

  if ! "${POST_DEPLOY_OK}"; then
    err "nginx /health の 5 連続 200 が 30 回試行 (約 90s) で達成できず。最終 status = ${POST_DEPLOY_CODE}"
    log "nginx -s reload で upstream の動的解決を強制..."
    if docker exec "${NGINX_CONTAINER}" nginx -s reload 2>&1; then
      sleep 5
      CONSECUTIVE_200=0
      FINAL_CODE=""
      for j in $(seq 1 10); do
        FINAL_CODE=$(curl -sf -o /dev/null -m 5 -w "%{http_code}" "${STAGING_HEALTH_URL}" || echo "000")
        if [[ "${FINAL_CODE}" == "200" ]]; then
          CONSECUTIVE_200=$((CONSECUTIVE_200 + 1))
          [[ "${CONSECUTIVE_200}" -ge 5 ]] && break
        else
          CONSECUTIVE_200=0
        fi
        sleep 2
      done
      log "nginx reload 後 /health 最終 status = ${FINAL_CODE}, consecutive 200 = ${CONSECUTIVE_200}/5"
      if [[ "${CONSECUTIVE_200}" -ge 5 ]]; then
        slack_notify "⚠️ [deploy_staging.sh] post-deploy nginx reload で 502 自動復旧"
        log "⚠️ nginx reload で復旧しました"
      else
        err "nginx reload 後も 5 連続 200 達成できず (最終 ${FINAL_CODE}). on_failure に遷移"
        on_failure
      fi
    else
      err "nginx -s reload が失敗"
      on_failure
    fi
  else
    log "✅ nginx /health = 5 連続 200 確認 OK"
  fi

elif "${BACKEND_ONLY}"; then
  log "バックエンドのみデプロイ (Blue/Green 切替, staging)"

  if ! deploy_backend_zero_downtime; then
    on_failure
  fi

  wait_healthy "http://127.0.0.1:${NGINX_PORT}/health" "nginx → backend (staging active)" || on_failure

else
  log "フルデプロイ開始（Staging環境）"
  log "初回起動時は active slot=blue で立ち上げ、以降は --backend-only で切替"

  log "📦 Pre-deploy backup (staging-new)..."
  ENVIRONMENT=staging-new bash "${SCRIPT_DIR}/backup_db.sh" || log "⚠️ Backup failed, continuing deploy..."

  log "upstream.conf を blue に初期化..."
  write_upstream_conf "blue"

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

    log "frontend / backend-blue / backend-green をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend-blue backend-green

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  log "全サービスを起動 (staging: postgres → backend-blue → nginx → frontend)"
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d
  ${DC} -f "${COMPOSE_FILE}" stop backend-green || true

  wait_healthy "http://127.0.0.1:${BLUE_PORT}/health"   "backend-blue (direct)"  || on_failure
  wait_healthy "http://127.0.0.1:${NGINX_PORT}/health"  "nginx → backend"        || on_failure
  wait_healthy "http://127.0.0.1:${FRONTEND_PORT}"      "frontend(staging)"      || on_failure
fi

# ───────────────────────────────────────────────
# Shadow Mode確認（デプロイ後）
# ───────────────────────────────────────────────
if ! "${FRONTEND_ONLY}"; then
  log "Shadow Mode最終確認..."
  HEALTH_JSON=$(curl -sf --max-time 5 "http://127.0.0.1:${NGINX_PORT}/health" 2>/dev/null || echo '{}')
  log "health: ${HEALTH_JSON}"
fi

# ───────────────────────────────────────────────
# nginx upstream 整合性チェック (warning only)
# ───────────────────────────────────────────────
check_nginx_upstream() {
  log "=== nginx upstream 整合性チェック ==="
  local active_slot
  active_slot=$(read_active_slot)
  if [ "${active_slot}" = "unknown" ]; then
    log "⚠️  WARNING: upstream.conf から active slot を判定できません"
    return
  fi
  log "  upstream.conf active slot: ${active_slot}"
  local nginx_running
  nginx_running=$(docker inspect --format='{{.State.Running}}' "${NGINX_CONTAINER}" 2>/dev/null || echo "false")
  if [ "${nginx_running}" != "true" ]; then
    log "⚠️  WARNING: nginx コンテナが稼働していません (${NGINX_CONTAINER})"
    return
  fi
  if curl -sf --max-time 3 "http://127.0.0.1:${NGINX_PORT}/nginx-health" >/dev/null 2>&1; then
    log "✅ nginx ${NGINX_PORT} → backend-${active_slot} 疎通 OK"
  else
    log "⚠️  WARNING: nginx ${NGINX_PORT} に到達できません"
  fi
}

if ! "${FRONTEND_ONLY}"; then
  check_nginx_upstream || true
fi

# ───────────────────────────────────────────────
# 最終ヘルスチェック
# ───────────────────────────────────────────────
log "=== 最終ヘルスチェック ==="

if ! "${FRONTEND_ONLY}"; then
  BE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${NGINX_PORT}/health" 2>/dev/null || echo "000")
  if [ "${BE_STATUS}" = "200" ]; then
    log "✅ backend  http://127.0.0.1:${NGINX_PORT}/health → ${BE_STATUS} (active=$(read_active_slot))"
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

slack_notify "✅ [deploy_staging.sh] Stagingデプロイ成功\n環境: staging (Shadow Mode)\nactive slot: $(read_active_slot)\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "Stagingデプロイ完了 (active slot: $(read_active_slot))"
