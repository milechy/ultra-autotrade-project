#!/bin/bash
set -euo pipefail

# ───────────────────────────────────────────────
# -v / --volumes フラグ誤使用防止ガード
# docker compose down -v はDBボリュームを削除してテスターデータが全滅する
# ───────────────────────────────────────────────
for _arg in "$@"; do
  if [[ "$_arg" == "-v" || "$_arg" == "--volumes" ]]; then
    echo "❌ ERROR: -v / --volumes フラグは禁止です。DBボリュームが削除されテスターデータが全て消えます。"
    echo "   down のみ使用してください: docker compose ... down"
    exit 1
  fi
done

# Ultra AutoTrade – production ワンショットデプロイスクリプト
# (2026-04-17 B案リネーム: 旧 deploy_staging.sh → deploy_production.sh)
# (2026-04-27 ゼロダウンタイム対応: --backend-only は Blue/Green 切替に変更)
#
# 使い方:
#   ./scripts/deploy_production.sh                  # フルデプロイ (初期 active=blue)
#   ./scripts/deploy_production.sh --frontend-only  # フロントエンドのみ
#   ./scripts/deploy_production.sh --backend-only   # Blue/Green 切替 (ゼロダウンタイム)
#   ./scripts/deploy_production.sh --no-build       # ビルドなし（up -d のみ）
#   ./scripts/deploy_production.sh --help

# ───────────────────────────────────────────────
# 定数
# ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"
# 2026-04-24 container_name 衝突インシデント後、*-production suffix に統一
FRONTEND_CONTAINER="ultra-autotrade-frontend-production"
BACKEND_BLUE_CONTAINER="ultra-autotrade-backend-blue-production"
BACKEND_GREEN_CONTAINER="ultra-autotrade-backend-green-production"
NGINX_CONTAINER="ultra-autotrade-nginx-production"
POSTGRES_CONTAINER="ultra-autotrade-postgres-production"
CLOUDFLARED_CONTAINER="ultra-autotrade-cloudflared-production"
HEALTH_TIMEOUT=60

# 本番イメージには alembic コンソールスクリプトが PATH に無い (システム python に
# alembic パッケージは在るが alembic.__main__ も無いため `python -m alembic` も不可)。
# コンテナ内で動く唯一の形 = console script の entry_point である alembic.config:main を
# python で直接起動する。cwd=/app/backend (compose の working_dir) が alembic.ini と
# env.py の `import app...` (alembic.ini: prepend_sys_path=.) を解決する。
# 配列で保持し "${ARR[@]}" 展開で python -c の引数を単一 argv として安全に渡す。
# (既存 idiom と同形: check_db_drift の model_columns 取得 `docker exec ... python -c ...`)
ALEMBIC_UPGRADE_HEAD=(python -c "from alembic.config import main; main(argv=['upgrade', 'head'])")
ALEMBIC_CHECK=(python -c "from alembic.config import main; main(argv=['check'])")

# Blue/Green host-side ports (compose の定義と一致させること)
BLUE_PORT=8010
GREEN_PORT=8011
NGINX_PORT=8080

UPSTREAM_CONF="${PROJECT_ROOT}/docker/nginx/upstream.production.conf"
LOCK_FILE="${PROJECT_ROOT}/.deploy-production.lock"

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
deploy_production.sh — Ultra AutoTrade production デプロイ

使い方:
  ./scripts/deploy_production.sh [OPTIONS]

オプション:
  --frontend-only   フロントエンドのみリビルド＆再起動
  --backend-only    Blue/Green 切替によるゼロダウンタイムデプロイ
  --no-build        ビルドなしで up -d のみ実行
  --help            このヘルプを表示

注意:
  - /opt/ultra-autotrade（または git root）から実行すること
  - .env.production が同ディレクトリに存在していること
  - Blue/Green 切替には docker/nginx/upstream.production.conf と nginx コンテナが必要
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

# upstream.conf から active slot を判定
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

# upstream.production.conf を書き換え (awk + cat >、sed -i / mv は禁止)
# cat > で in-place 書き換えすることで inode を保持し bind-mount を維持する。
# nginx 未起動時は docker exec をスキップ (フルデプロイ・リカバリ時のフェイルセーフ)。
write_upstream_conf() {
  local new_slot="$1"  # blue or green
  local tmp_file
  tmp_file=$(mktemp "${UPSTREAM_CONF}.XXXXXX")
  # 2026-05-12 以降の新形式: nginx.conf の resolver + 変数 proxy_pass と対になる。
  # `set $backend backend-blue:8000;` を nginx の `location /` で include し、
  # `proxy_pass http://$backend;` に渡す。resolver 127.0.0.11 valid=5s で TTL 解決。
  # 旧形式 `server backend-blue:8000 ...;` は upstream block 専用で hostname 固着の元凶だった。
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

# 現在 active な backend コンテナ名を返す (DB drift / 401 チェック用)
active_backend_container() {
  local slot
  slot=$(read_active_slot)
  if [[ "${slot}" = "green" ]]; then
    echo "${BACKEND_GREEN_CONTAINER}"
  else
    echo "${BACKEND_BLUE_CONTAINER}"
  fi
}

# Blue/Green ゼロダウンタイム切替
deploy_backend_zero_downtime() {
  local active_slot inactive_slot inactive_port
  active_slot=$(read_active_slot)

  if [[ "${active_slot}" = "blue" ]]; then
    inactive_slot="green"; inactive_port="${GREEN_PORT}"
  elif [[ "${active_slot}" = "green" ]]; then
    inactive_slot="blue";  inactive_port="${BLUE_PORT}"
  else
    err "upstream.conf から active slot を判定できません: ${UPSTREAM_CONF}"
    err "復旧: 手動で upstream.conf に 'set \$backend backend-blue:8000;' を書き、nginx を起動してください"
    return 1
  fi

  log "Blue/Green 切替開始: active=${active_slot} → new=${inactive_slot}(:${inactive_port})"

  # 1. 新コンテナをビルド (旧コンテナは稼働継続)
  if ! "${NO_BUILD}"; then
    log "backend-${inactive_slot} をビルド中..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build "backend-${inactive_slot}"
  fi

  # 1b. Stream 4 (2026-05-21): ACTIVE_BACKEND_COLOR を .env.production に書き込む
  # 新コンテナ起動(step 2)より前に確定させることで、新コンテナが正しい color を読んで起動し
  # scheduler color ガードが「自分 = active」と正しく判定できる。
  # awk + tmpfile + cat > で inode 保持（sed -i 禁止ルール / mv は bind-mount を壊す）。
  log "ACTIVE_BACKEND_COLOR を ${inactive_slot} に更新 (${ENV_FILE})..."
  local _env_tmp
  _env_tmp=$(mktemp "${ENV_FILE}.XXXXXX")
  if grep -q '^ACTIVE_BACKEND_COLOR=' "${ENV_FILE}"; then
    awk -v slot="${inactive_slot}" '{
      if ($0 ~ /^ACTIVE_BACKEND_COLOR=/) {
        print "ACTIVE_BACKEND_COLOR=" slot
      } else {
        print
      }
    }' "${ENV_FILE}" > "${_env_tmp}"
  else
    awk '{print}' "${ENV_FILE}" > "${_env_tmp}"
    printf '\nACTIVE_BACKEND_COLOR=%s\n' "${inactive_slot}" >> "${_env_tmp}"
  fi
  cat "${_env_tmp}" > "${ENV_FILE}"
  rm -f "${_env_tmp}"
  log "ACTIVE_BACKEND_COLOR=${inactive_slot} → ${ENV_FILE} に書き込み完了"

  # 2. 新コンテナを起動 (--no-deps で他サービスに影響を与えない)
  log "backend-${inactive_slot} を起動..."
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps "backend-${inactive_slot}"

  # 2a. DB マイグレーション (swap 前に実行、失敗時は abort)
  ALEMBIC_CONT="ultra-autotrade-backend-${inactive_slot}-production"
  log "alembic upgrade head を実行 (コンテナ: ${ALEMBIC_CONT})..."
  if ! docker exec "${ALEMBIC_CONT}" "${ALEMBIC_UPGRADE_HEAD[@]}"; then
    err "alembic upgrade head 失敗。切替を中止し新コンテナを停止します"
    ${DC} -f "${COMPOSE_FILE}" stop "backend-${inactive_slot}" 2>/dev/null || true
    exit 1
  fi
  log "✅ alembic upgrade head 完了"

  # 3. 新コンテナのヘルスチェック (ホスト側ポート直打ち)
  if ! wait_healthy "http://127.0.0.1:${inactive_port}/health" "backend-${inactive_slot}"; then
    err "新コンテナのヘルスチェック失敗。切替を中止し新コンテナを停止します"
    ${DC} -f "${COMPOSE_FILE}" stop "backend-${inactive_slot}" 2>/dev/null || true
    return 1
  fi

  # 4. nginx upstream を切替 (awk + 一時ファイル + cat >)
  log "upstream.conf を ${inactive_slot} に書き換え..."
  write_upstream_conf "${inactive_slot}"

  # 5. nginx -s reload (POSIX 仕様で既存接続を引き継ぐ → ゼロダウンタイム保証)
  log "nginx -s reload を実行..."
  if ! docker exec "${NGINX_CONTAINER}" nginx -s reload; then
    err "nginx reload 失敗。upstream.conf を ${active_slot} に戻して再 reload..."
    write_upstream_conf "${active_slot}"
    docker exec "${NGINX_CONTAINER}" nginx -s reload || true
    return 1
  fi
  log "✅ nginx upstream → backend-${inactive_slot} 切替完了"

  # 6. 30秒待機 (既存接続の収束)
  log "30秒待機して既存接続が収束するのを待つ..."
  sleep 30

  # 7. 旧コンテナを stop (rm はしない、緊急ロールバックに備えて停止状態で残す)
  log "backend-${active_slot} を stop (緊急ロールバック用に rm はしない)..."
  ${DC} -f "${COMPOSE_FILE}" stop "backend-${active_slot}"

  log "✅ Blue/Green 切替完了: active=${inactive_slot}"
  log "   ロールバック手順: docker/nginx/upstream.production.conf を 'set \$backend backend-${active_slot}:8000;' に書き戻し、"
  log "                  ${DC} -f ${COMPOSE_FILE} start backend-${active_slot} → docker exec ${NGINX_CONTAINER} nginx -s reload"
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
    --skip-gate)     ;;  # launch_gate bypass — 後段で処理
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

# .env ファイルのパーミッション検証 (600 必須 / 2026-05-19 セキュリティガード追加)
_ENV_PERM=$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%OLp' "${ENV_FILE}" 2>/dev/null || echo "unknown")
if [[ "${_ENV_PERM}" != "600" ]]; then
  err "${ENV_FILE} のパーミッションが ${_ENV_PERM} です。600 でなければデプロイを中止します。"
  err "修正: chmod 600 ${ENV_FILE}"
  exit 1
fi

if [[ ! -f "${UPSTREAM_CONF}" ]]; then
  err "${UPSTREAM_CONF} が見つかりません — Blue/Green 構成が壊れている可能性"
  err "復旧: docker/nginx/upstream.production.conf を 'set \$backend backend-blue:8000;' で作成してください"
  exit 1
fi

# === デプロイの同時実行排除 (flock) ===
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
  err "別のデプロイが進行中です: ${LOCK_FILE}"
  err "進行中のデプロイが終わるか、ロックが古い場合は手動で削除してから再実行してください"
  exit 1
fi

# === Production deploy guardrails (2026-04-19 根本解決原則) ===
# .env.production が本番固有の値を持っていることを保証する予防層。
# 2026-04-18 sed 一斉更新インシデント再発防止。

# Guard 1: .env.production 必須キー検証
if ! grep -q '^APP_ENV=production$' .env.production; then
  echo "❌ FAIL: .env.production に APP_ENV=production がない"
  exit 1
fi

if grep -qE '^BYBIT_SANDBOX=true' .env.production; then
  echo "❌ FAIL: .env.production で BYBIT_SANDBOX=true (本番は false 必須)"
  exit 1
fi

if grep -qE '^AAVE_NETWORK=.*sepolia' .env.production; then
  if [[ "${FRONTEND_ONLY}" == "true" ]]; then
    echo "⚠️  WARN: AAVE_NETWORK に sepolia が含まれています (フロントエンドのみデプロイのためスキップ)"
  elif [[ "${ALLOW_TESTNET:-0}" == "1" ]]; then
    # Partner 先行検証フェーズ等の意図的な testnet 運用を許容
    # docs/22_production_release_checklist.md §「ALLOW_TESTNET bypass」参照
    printf '\033[1;31m⚠️  ALLOW_TESTNET=1: AAVE_NETWORK に sepolia 含むまま production deploy 続行\033[0m\n'
    printf '\033[1;31m⚠️  この bypass は partner 先行検証フェーズの意図的な testnet 運用専用です\033[0m\n'
    printf '\033[1;31m⚠️  mainnet 移行後は ALLOW_TESTNET 環境変数を外してください\033[0m\n'
  else
    echo "❌ FAIL: .env.production で AAVE_NETWORK に sepolia 含む (本番は mainnet 必須)"
    echo "    意図的な testnet 運用 (partner 先行検証等) の場合は ALLOW_TESTNET=1 を環境変数で指定してください"
    exit 1
  fi
fi

# Guard 1b: NEXT_PUBLIC_PRIVY_APP_ID 検証 (フロント build に焼き込まれる build-time 値)
# 未設定/placeholder のまま build すると PrivyRootClient が PrivyProvider を描画せず、
# ログイン画面で usePrivy が throw → 白画面でログイン不能になる (PrivyRootClient.tsx)。
# build 前にここで弾く (フロントを焼く full / --frontend-only の両方で必須)。
_privy_app_id="$(grep -E '^NEXT_PUBLIC_PRIVY_APP_ID=' .env.production | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]' || true)"
if [[ -z "${_privy_app_id}" || "${_privy_app_id}" == "clplaceholder000000000000000000000" ]]; then
  echo "❌ FAIL: .env.production の NEXT_PUBLIC_PRIVY_APP_ID が未設定/placeholder"
  echo "    → Privy ログインが白画面になります。実 App ID を設定してから deploy してください"
  exit 1
fi

# Guard 2: 環境分離チェック (バックエンドに関わるキーのみ必須 — フロントエンドのみデプロイ時はスキップ)
if [[ "${FRONTEND_ONLY}" == "true" ]]; then
  echo "⚠️  WARN: --frontend-only のため環境分離チェックをスキップ (バックエンド変更なし)"
else
  bash scripts/check_env_separation.sh || {
    echo "❌ FAIL: 環境分離チェック失敗"
    exit 1
  }
fi

# Guard 3: compose file 指定確認
if [[ "${COMPOSE_FILE}" != *production.yml* ]] && [[ -z "${FORCE_OVERRIDE:-}" ]]; then
  echo "❌ FAIL: 本番デプロイは docker-compose.production.yml 必須"
  echo "   (テスター期間の例外で staging.yml を使う場合は FORCE_OVERRIDE=1 を設定)"
  exit 1
fi

# Guard 4: DB schema gap check (exit 1 aborts deploy, exit 2 is warning only)
if [[ "${FRONTEND_ONLY}" != "true" ]]; then
  echo "[deploy] Checking DB schema gaps..."
  set +e
  bash "${SCRIPT_DIR}/check_db_migration_gap.sh"
  _gap_exit=$?
  set -e
  if [[ "${_gap_exit}" -eq 1 ]]; then
    echo "FAIL: DB schema gap detected -- run ALTER TABLE statements then redeploy"
    echo "   To skip: SKIP_DB_GAP_CHECK=1 ./scripts/deploy_production.sh"
    if [[ -z "${SKIP_DB_GAP_CHECK:-}" ]]; then
      exit 1
    fi
    echo "WARN: SKIP_DB_GAP_CHECK=1 set -- continuing despite schema gap"
  elif [[ "${_gap_exit}" -eq 2 ]]; then
    echo "WARN: DB gap check skipped (DB unreachable or config error)"
  else
    echo "DB schema: no gaps detected"
  fi
fi

echo "✅ All production deploy guards passed"
# === End of guardrails ===

# ───────────────────────────────────────────────
# Launch Gate (L0-L5)
# 2026-05-27 追加 (Asana 1215151958676195 / [LAUNCH-GATE-B]):
#   schema / env / smoke / e2e / kill switch / wiring lint を一括で
#   deploy 時 gate として実行する。失敗時 deploy 中止。
#
#   緊急時 bypass:
#     SKIP_LAUNCH_GATE=1 ./scripts/deploy_production.sh
#     ./scripts/deploy_production.sh --skip-gate
#
#   launch_gate.sh は別タスク A が作成中。未配置の場合は WARN ログのみで続行。
# ───────────────────────────────────────────────
_SKIP_GATE=0
for _arg in "$@"; do
  if [[ "${_arg}" == "--skip-gate" ]]; then
    _SKIP_GATE=1
  fi
done

if [[ "${SKIP_LAUNCH_GATE:-0}" == "1" || "${_SKIP_GATE}" == "1" ]]; then
  log "⚠️  WARN: launch_gate を skip しました (SKIP_LAUNCH_GATE=${SKIP_LAUNCH_GATE:-0} / --skip-gate=${_SKIP_GATE})"
else
  if [[ -x "${SCRIPT_DIR}/launch_gate.sh" ]]; then
    log "Running launch_gate (set SKIP_LAUNCH_GATE=1 or --skip-gate to bypass)"
    # L2 smoke の対象ポートを現 active slot から動的に決定する。
    # launch_gate は deploy_backend_zero_downtime() より前に実行されるため、
    # 現時点での active が正しい smoke 対象（deploy 前の正常確認）。
    _active_slot_now="$(read_active_slot 2>/dev/null || echo 'blue')"
    if [[ "${_active_slot_now}" == "blue" ]]; then
      _smoke_port="${BLUE_PORT}"
    else
      _smoke_port="${GREEN_PORT}"
    fi
    log "L2 smoke 対象: backend-${_active_slot_now} (port ${_smoke_port})"
    if ! LAUNCH_GATE_BASE_URL="http://127.0.0.1:${_smoke_port}" \
         "${SCRIPT_DIR}/launch_gate.sh" --env=production --skip=L3,L4; then
      err "launch_gate failed. Aborting deploy."
      exit 1
    fi
    log "✅ launch_gate passed"
  else
    log "ℹ️  launch_gate.sh not found yet (待機中: tasks/A 着手前) — skipping"
  fi
fi

DC=$(resolve_dc)
log "docker compose コマンド: ${DC}"
log "現在の active slot: $(read_active_slot)"

# ───────────────────────────────────────────────
# 共通ステップ 1-4
# ───────────────────────────────────────────────
log "git pull origin main"
git pull origin main

log ".env.production を読み込み（ビルド ARG 用）"
# shellcheck disable=SC2046
export $(grep -v '^#' "${ENV_FILE}" | grep '=' | xargs)

# デプロイ版識別子: PostHog の app_version（全イベント super property）に git short SHA を埋め込む。
# バージョンアップ前後の行動比較を可能にする。git 失敗時は dev フォールバック。
export NEXT_PUBLIC_APP_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
log "NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION} を frontend build ARG に埋め込み"

# ───────────────────────────────────────────────
# モード別デプロイ
# ───────────────────────────────────────────────
on_failure() {
  err "デプロイ失敗。コンテナログ末尾:"
  ${DC} -f "${COMPOSE_FILE}" logs --tail=20 2>/dev/null || true
  slack_notify "❌ [deploy_production.sh] デプロイ失敗\n原因: ヘルスチェックタイムアウトまたはビルドエラー"
  exit 1
}
trap on_failure ERR

if "${FRONTEND_ONLY}"; then
  # ─── フロントエンドのみ ───────────────────────
  log "フロントエンドのみデプロイ"

  if ! "${NO_BUILD}"; then
    log "frontend をビルド中（コンテナ停止前にビルド先行）..."
    # ビルドを先行させる。旧順序（stop → rmi → build）だとビルド失敗時に
    # コンテナもイメージも消えて起動不可になる。
    # 2026-05-13 RCA: GID 1214762107679590
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
  fi

  log "旧 frontend コンテナを停止・削除..."
  ${DC} -f "${COMPOSE_FILE}" stop frontend
  docker rm -f "${FRONTEND_CONTAINER}" 2>/dev/null || true

  if ! "${NO_BUILD}"; then
    log "dangling（タグなし）イメージを削除..."
    docker image prune -f 2>/dev/null || true

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  # CLAUDE.md「本番フロントエンド操作ルール」(L1009) 遵守:
  # --no-deps --force-recreate なしで `up -d frontend` を実行すると
  # docker compose が依存関係を再評価し、backend を含む依存サービスが
  # recreate されて Docker bridge IP が変動 → nginx の upstream IP 固着で 502。
  # 2026-05-12 RCA / docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md 参照。
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
    up -d --no-deps --force-recreate frontend

  wait_healthy "http://localhost:3000" "frontend" || on_failure

  log "フロントエンド チャンク数確認..."
  CHUNK_COUNT=$(docker exec "${FRONTEND_CONTAINER}" \
    sh -c "ls /app/.next/static/chunks/ 2>/dev/null | wc -l" || echo "0")
  log "  .next/static/chunks/ ファイル数: ${CHUNK_COUNT}"
  if [ "${CHUNK_COUNT}" -lt 5 ]; then
    log "⚠️  WARNING: チャンク数が少ない（${CHUNK_COUNT}）。ビルドが正常に完了していない可能性があります"
  else
    log "✅ チャンク生成確認 (${CHUNK_COUNT} files)"
  fi

  # ─── post-deploy: Cloudflare 経由 /health 疎通テスト (Gate 8) ───
  # 2026-05-12 教訓: 内部 localhost:3000 ヘルスチェックだけでは
  # nginx → backend 経路の障害 (upstream IP 固着) を検出できない。
  # Cloudflare → cloudflared → nginx → backend の外形パスが**安定して**通っているか
  # 確認するため、5 回**連続**で 200 を要求する。途中で 502 等が出たらカウンタをリセット。
  # 最大 30 回 (約 90s) で 5 連続 200 を達成できなければ nginx -s reload を試行。
  log "post-deploy: Cloudflare 経由 /health で外形疎通を 5 連続 200 で確認..."
  EXTERNAL_HEALTH_URL="https://api.ultra-auto-trade.com/health"
  POST_DEPLOY_OK=false
  CONSECUTIVE_200=0
  POST_DEPLOY_CODE=""
  for i in $(seq 1 30); do
    POST_DEPLOY_CODE=$(curl -sf -o /dev/null -m 5 -w "%{http_code}" "${EXTERNAL_HEALTH_URL}" || echo "000")
    if [[ "${POST_DEPLOY_CODE}" == "200" ]]; then
      CONSECUTIVE_200=$((CONSECUTIVE_200 + 1))
      log "  外形 /health [attempt ${i}] = 200 (consecutive ${CONSECUTIVE_200}/5)"
      if [[ "${CONSECUTIVE_200}" -ge 5 ]]; then
        POST_DEPLOY_OK=true
        break
      fi
    else
      log "  外形 /health [attempt ${i}] = ${POST_DEPLOY_CODE} (consecutive reset 0/5)"
      CONSECUTIVE_200=0
    fi
    sleep 3
  done

  if ! "${POST_DEPLOY_OK}"; then
    err "外形 /health の 5 連続 200 が 30 回試行 (約 90s) で達成できず。最終 status = ${POST_DEPLOY_CODE}"
    err "  (nginx upstream IP 固着・cloudflared 伝播遅延・backend 起動失敗のいずれか)"
    log "nginx -s reload で upstream の動的解決を強制..."
    if docker exec "${NGINX_CONTAINER}" nginx -s reload 2>&1; then
      sleep 5
      # reload 後も 5 連続 200 を要求
      CONSECUTIVE_200=0
      FINAL_CODE=""
      for j in $(seq 1 10); do
        FINAL_CODE=$(curl -sf -o /dev/null -m 5 -w "%{http_code}" "${EXTERNAL_HEALTH_URL}" || echo "000")
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
        slack_notify "⚠️ [deploy_production.sh] post-deploy nginx reload で 502 自動復旧 (frontend-only deploy 直後)\\n要調査: nginx の resolver 設定が機能しているか、または backend container が想定外に recreate されていないか"
        log "⚠️ nginx reload で復旧しました (要 RCA)"
      else
        err "nginx reload 後も 5 連続 200 達成できず (最終 ${FINAL_CODE}). on_failure に遷移"
        on_failure
      fi
    else
      err "nginx -s reload が失敗"
      on_failure
    fi
  else
    log "✅ 外形 /health = 5 連続 200 確認 OK (Gate 8)"
  fi

elif "${BACKEND_ONLY}"; then
  # ─── バックエンドのみ (Blue/Green ゼロダウンタイム) ───
  log "バックエンドのみデプロイ (Blue/Green 切替)"

  if ! deploy_backend_zero_downtime; then
    on_failure
  fi

  # nginx 経由のヘルスチェック (cloudflared が見るのと同じ経路)
  wait_healthy "http://localhost:${NGINX_PORT}/health" "nginx → backend (active)" || on_failure

else
  # ─── フルデプロイ ──────────────────────────────
  log "フルデプロイ開始"
  log "初回起動時は active slot=blue で立ち上げ、以降は --backend-only で切替"

  log "📦 Pre-deploy backup (production)..."
  ENVIRONMENT=production bash "${SCRIPT_DIR}/backup_db.sh" || log "⚠️ Backup failed, continuing deploy..."

  # 既知のフルデプロイは active=blue で再開する。upstream.conf を blue に揃える。
  log "upstream.conf を blue に初期化..."
  write_upstream_conf "blue"

  # ── 新イメージを down 前にビルド ──
  # 下記「down 前 migration」を新 migration 入りの使い捨てコンテナで先行実行するため、
  # 新イメージは down より前に確定している必要がある (旧コンテナは稼働継続のまま)。
  if ! "${NO_BUILD}"; then
    log "古いフロントエンドイメージを完全削除..."
    docker images --format "{{.Repository}} {{.ID}}" \
      | grep -E "frontend|ultra-autotrade.*front" \
      | awk '{print $2}' \
      | xargs -r docker rmi -f 2>/dev/null || true

    log "frontend / backend-blue / backend-green をビルド中（frontend は --no-cache）..."
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend
    ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend-blue backend-green

    log "古いビルドキャッシュを削除（1時間以上前のエントリ）..."
    docker builder prune --filter until=1h -f 2>/dev/null || true
  fi

  # ── DB マイグレーション (down 前・旧コンテナ稼働中の先行実行) ──
  # 旧 backend が旧コードのまま traffic を受けている間に、新 migration を使い捨てコンテナで
  # 先行適用する。migration は additive 後方互換のため、旧コードは新列の増加に影響されない。
  # 失敗時は down せず exit 1 → production は一切停止せず無傷のまま中断できる。
  # network / image / env_file の解決は compose に委譲。--no-deps で稼働中 postgres を再起動しない。
  # 2026-06-04 本番事故: alembic upgrade head 未実行により migration gap が L0 に 3 回露出。
  log "postgres が ready になるまで待機 (最大 30s)..."
  for _pg_i in $(seq 1 10); do
    if docker exec "${POSTGRES_CONTAINER}" pg_isready -U ultra >/dev/null 2>&1; then
      log "postgres ready"
      break
    fi
    sleep 3
  done
  log "alembic upgrade head を実行 (フルデプロイ: 使い捨てコンテナ, down 前先行適用)..."
  if ! ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm -T --no-deps backend-blue "${ALEMBIC_UPGRADE_HEAD[@]}"; then
    err "alembic upgrade head 失敗。down せずデプロイを中止します (production 無傷)"
    exit 1
  fi
  log "✅ alembic upgrade head 完了 (down 前先行適用)"

  log "本番コンテナを停止・削除 (--remove-orphans 禁止: staging-new 道連れ防止)"
  ${DC} -f "${COMPOSE_FILE}" down

  # 本番コンテナ (*-production) と移行前の旧 *-staging 残留のみ強制削除。
  # *-staging-new (真の staging 環境) は保護対象なので除外する。
  docker ps -a --format '{{.Names}}' \
    | grep -E '^ultra-autotrade-[a-z-]+-(production|staging)$' \
    | xargs -r docker rm -f 2>/dev/null || true

  log "未使用ボリュームを削除（DBボリュームは名前付きのため保護される）..."
  docker volume prune -f 2>/dev/null || true

  log "全サービスを起動 (postgres → backend-blue → nginx → frontend → cloudflared)"
  # 注意: 初回フルデプロイ時は backend-blue のみ起動状態にし、green は手動で起動するまで停止。
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d
  # green は full deploy 直後は不要なため停止しておく (RAM 節約)
  ${DC} -f "${COMPOSE_FILE}" stop backend-green || true

  wait_healthy "http://127.0.0.1:${BLUE_PORT}/health"     "backend-blue (direct)"   || on_failure
  wait_healthy "http://localhost:${NGINX_PORT}/health"    "nginx → backend"         || on_failure
  wait_healthy "http://localhost:3000"                    "frontend"                || on_failure
fi

# ───────────────────────────────────────────────
# スケジューラー健全性チェック（警告のみ、デプロイは止めない）
# ───────────────────────────────────────────────
if ! "${FRONTEND_ONLY}"; then
  log "15秒待機してスケジューラー状態を確認中..."
  sleep 15
  HEALTH_JSON=$(curl -sf --max-time 5 "http://localhost:${NGINX_PORT}/health" 2>/dev/null || echo '{}')
  SCHED_HEALTHY=$(echo "${HEALTH_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_healthy','unknown'))" 2>/dev/null || echo "unknown")
  if [ "${SCHED_HEALTHY}" = "False" ] || [ "${SCHED_HEALTHY}" = "false" ]; then
    log "⚠️  WARNING: scheduler_healthy=false — スケジューラーが overdue 状態です"
    log "   詳細: ${HEALTH_JSON}"
  elif [ "${SCHED_HEALTHY}" = "unknown" ]; then
    log "⚠️  WARNING: /health からスケジューラー状態を取得できませんでした"
  else
    log "scheduler_healthy=${SCHED_HEALTHY} ✓"
  fi

  # scheduler_last_error チェック (KeyError 等の runtime エラーを検知)
  # 2026-05-19 インシデント: v4 prompt deploy 後 KeyError が 14 分見逃された再発防止
  SCHED_LAST_ERROR=$(echo "${HEALTH_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_last_error') or '')" 2>/dev/null || echo "")
  if [ -n "${SCHED_LAST_ERROR}" ]; then
    log "⚠️  WARNING: scheduler_last_error 検出 — 最後の判定実行でエラーが発生しています"
    log "   エラー内容: ${SCHED_LAST_ERROR}"
    log "   → AI_PROMPT_VERSION 等の設定を確認してください"
    log "   → 必要に応じて前バージョンにロールバックしてください"
  else
    log "scheduler_last_error=なし ✓"
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
    local container_running
    container_running=$(docker inspect --format='{{.State.Running}}' \
      "${CLOUDFLARED_CONTAINER}" 2>/dev/null || echo "false")
    if [ "${container_running}" = "true" ]; then
      log "✅ cloudflared コンテナ稼働中"
    else
      log "⚠️  WARNING: Cloudflare Tunnel が検出されませんでした"
      log "   → フロントエンド(:3000) + バックエンド(:${NGINX_PORT}) 両方のトンネルが必要"
      log "   → docker compose logs ${CLOUDFLARED_CONTAINER} で確認してください"
    fi
  fi
}

# 検証 3: DB migration drift 検出 (active slot のコンテナを参照)
check_db_drift() {
  log "=== DB migration drift チェック ==="
  local active_container
  active_container=$(active_backend_container)
  log "  active backend container: ${active_container}"

  # 主判定: alembic check — DB が head revision と完全一致するか
  # (テーブル/列の存在チェックでなく alembic_version と実 schema の突合)
  if docker exec "${active_container}" "${ALEMBIC_CHECK[@]}" >/dev/null 2>&1; then
    log "✅ alembic check OK: DB は head revision に一致 (未適用 migration なし)"
  else
    local _alembic_current
    _alembic_current=$(docker exec "${POSTGRES_CONTAINER}" \
      psql -U ultra -d ultra_autotrade -t -c \
      "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1;" \
      2>/dev/null | tr -d ' \n' || echo "unknown")
    log "⚠️  WARNING: alembic check 失敗 — 未適用 migration あり (現 DB revision: ${_alembic_current})"
    log "   → alembic upgrade head を実行してください"
    log "   → ./scripts/deploy_production.sh --backend-only で再デプロイすると自動適用されます"
  fi

  # 補完チェック: users テーブルのカラム drift (alembic check を補完、モグラ叩き早期検知)
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
  model_columns=$(docker exec "${active_container}" python -c \
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
    log "✅ users テーブルカラム drift なし"
  fi
}

# 検証 4: 401 エラー確認（INTERNAL_API_TOKEN 問題検出）
check_auth_errors() {
  log "=== 内部 API 認証エラーチェック ==="
  local active_container
  active_container=$(active_backend_container)
  local auth_errors
  auth_errors=$(docker logs "${active_container}" 2>&1 | tail -100 \
    | grep -c "401 Unauthorized" || echo "0")
  if [ "${auth_errors}" -gt 5 ]; then
    log "⚠️  WARNING: 直近100行に 401 Unauthorized が ${auth_errors} 件 (${active_container})"
    log "   → INTERNAL_API_TOKEN が .env.production に設定されているか確認してください"
  else
    log "✅ 401 エラー ${auth_errors} 件（正常範囲）"
  fi
}

# 検証 5: CORS preflight 自動検証
check_cors() {
  log "=== CORS preflight チェック ==="
  local frontend_origin="${CORS_ORIGINS:-https://app.ultra-auto-trade.com}"
  frontend_origin="${frontend_origin%%,*}"  # 最初のオリジンのみ使用
  local cors_header
  cors_header=$(curl -s -I \
    -H "Origin: ${frontend_origin}" \
    -H "Access-Control-Request-Method: GET" \
    --max-time 5 \
    "http://localhost:${NGINX_PORT}/health" 2>/dev/null \
    | grep -i "access-control-allow-origin" | tr -d '\r' || echo "")
  if echo "${cors_header}" | grep -q "${frontend_origin}\|\*"; then
    log "✅ CORS: ${frontend_origin} が許可されています"
  else
    log "⚠️  WARNING: CORS ヘッダーに ${frontend_origin} が含まれていません"
    log "   → .env.production の CORS_ORIGINS に ${frontend_origin} を追加してください"
    log "   → レスポンス: ${cors_header:-（ヘッダーなし）}"
  fi
}

# 検証 6: nginx upstream 整合性 (active slot と nginx upstream の一致確認)
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
  # nginx 経由でアクセスして応答を確認
  if curl -sf --max-time 3 "http://localhost:${NGINX_PORT}/nginx-health" >/dev/null 2>&1; then
    log "✅ nginx ${NGINX_PORT} → backend-${active_slot} 疎通 OK"
  else
    log "⚠️  WARNING: nginx ${NGINX_PORT} に到達できません"
  fi
}

# 全追加検証を実行（各ステップは独立して動作）
run_post_deploy_checks() {
  log "=== デプロイ後追加検証 開始 ==="
  check_mixed_content   || true
  check_tunnel          || true
  check_db_drift        || true
  check_auth_errors     || true
  check_cors            || true
  check_nginx_upstream  || true
  log "=== デプロイ後追加検証 完了 ==="
}

if ! "${BACKEND_ONLY}"; then
  run_post_deploy_checks
else
  # backend-only でも nginx upstream 整合性は確認したい
  check_nginx_upstream || true
fi

# ───────────────────────────────────────────────
# 最終ヘルスチェック（HTTP ステータス確認）
# ───────────────────────────────────────────────
log "=== 最終ヘルスチェック ==="

# バックエンド (nginx 経由)
if ! "${FRONTEND_ONLY}"; then
  BE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${NGINX_PORT}/health" 2>/dev/null || echo "000")
  if [ "${BE_STATUS}" = "200" ]; then
    log "✅ backend  http://localhost:${NGINX_PORT}/health → ${BE_STATUS} (active=$(read_active_slot))"
  else
    log "⚠️  WARNING: backend  http://localhost:${NGINX_PORT}/health → ${BE_STATUS}"
  fi
fi

# フロントエンド
if ! "${BACKEND_ONLY}"; then
  FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:3000 2>/dev/null || echo "000")
  if [ "${FE_STATUS}" = "200" ]; then
    log "✅ frontend http://localhost:3000 → ${FE_STATUS}"
  else
    log "⚠️  WARNING: frontend http://localhost:3000 → ${FE_STATUS} (リダイレクトや初期化中の可能性あり)"
  fi
fi

log "=== 最終ヘルスチェック 完了 ==="

# ───────────────────────────────────────────────
# 完了報告
# ───────────────────────────────────────────────
log "コンテナ状態:"
${DC} -f "${COMPOSE_FILE}" ps

slack_notify "✅ [deploy_production.sh] デプロイ成功\n環境: production\nactive slot: $(read_active_slot)\nブランチ: $(git rev-parse --abbrev-ref HEAD) ($(git rev-parse --short HEAD))"

log "デプロイ完了 (active slot: $(read_active_slot))"
