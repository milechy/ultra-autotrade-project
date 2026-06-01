#!/bin/bash
# scripts/deploy_6_1_bundle.sh  v2  (2026-06-01)
#
# 6/1 partner 実売買デプロイバンドル — 人間確認付き段階実行
#
# 前提:
#   - 本番 VPS (/opt/ultra-autotrade) で ultra ユーザーとして実行
#   - .env.production が存在し chmod 600 であること
#   - ALLOW_TESTNET=1 が export 済み (Sepolia guard bypass)
#
# 実行:
#   cd /opt/ultra-autotrade
#   bash scripts/deploy_6_1_bundle.sh
#
# 各 PHASE 末に「続行しますか？ [y/N]」プロンプトが出る。
# 'y' 以外はすべて中止。

set -euo pipefail

# ──────────────────────────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.production"
POSTGRES_CONTAINER="ultra-autotrade-postgres-production"
FRONTEND_CONTAINER="ultra-autotrade-frontend-production"
NGINX_PORT=8080
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy_production.sh"

log()  { echo "[bundle] $*"; }
err()  { echo "[bundle] ERROR: $*" >&2; }

# ──────────────────────────────────────────────────────────────────
# 人間確認ストップ
# ──────────────────────────────────────────────────────────────────
human_confirm() {
  local phase_name="$1"
  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "  ${phase_name} 完了。上記の出力を確認してください。"
  echo "═══════════════════════════════════════════════════════════════"
  read -r -p "  続行しますか？ [y/N]: " ans
  if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
    log "ユーザーにより中止されました (phase=${phase_name})"
    exit 0
  fi
  echo ""
}

# ──────────────────────────────────────────────────────────────────
# 前提チェック
# ──────────────────────────────────────────────────────────────────
cd "${PROJECT_ROOT}"
log "project root: ${PROJECT_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
  err "${ENV_FILE} が見つかりません — 中止します"
  exit 1
fi

_ENV_PERM=$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%OLp' "${ENV_FILE}" 2>/dev/null || echo "unknown")
if [[ "${_ENV_PERM}" != "600" ]]; then
  err "${ENV_FILE} のパーミッションが ${_ENV_PERM} です。chmod 600 してから再実行してください"
  exit 1
fi

if [[ ! -x "${DEPLOY_SCRIPT}" ]]; then
  err "${DEPLOY_SCRIPT} が見つかりません"
  exit 1
fi

# ──────────────────────────────────────────────────────────────────
# PHASE 1: git pull origin main (272ca45 = #454+#476 込み)
# ──────────────────────────────────────────────────────────────────
echo ""
log "══════ PHASE 1: git pull origin main ══════"

git pull origin main

CURRENT_COMMIT=$(git rev-parse --short HEAD)
log "現在の HEAD: ${CURRENT_COMMIT}"
log "期待: 272ca45 (または #476 を含む main の先端)"

# #476 が含まれているか proposals/router.py の expected_from で確認
if grep -q "expected_from" "${PROJECT_ROOT}/backend/app/proposals/router.py" 2>/dev/null; then
  log "✅ #476 (expected_from/expected_to) が含まれています"
else
  err "#476 の変更が見当たりません。git log を確認してください"
  git log --oneline -5
  exit 1
fi

human_confirm "PHASE 1 (git pull)"

# ──────────────────────────────────────────────────────────────────
# PHASE 2: .env.production への AUTO_EXECUTION_ENABLED=false 追記
# ──────────────────────────────────────────────────────────────────
echo ""
log "══════ PHASE 2: .env.production 追記 ══════"

# 現在の関連キー確認
log "--- 現在の .env.production 関連キー ---"
grep -E "^AUTO_EXECUTION_ENABLED|^REBALANCE_SHADOW_MODE|^POLICY_" "${ENV_FILE}" || log "(該当キーなし)"
echo ""

# AUTO_EXECUTION_ENABLED が既に存在するか確認
if grep -q '^AUTO_EXECUTION_ENABLED=' "${ENV_FILE}"; then
  CURRENT_AEE=$(grep '^AUTO_EXECUTION_ENABLED=' "${ENV_FILE}" | head -1 | cut -d= -f2-)
  log "AUTO_EXECUTION_ENABLED は既に存在: ${CURRENT_AEE}"
  if [[ "${CURRENT_AEE}" == "false" ]]; then
    log "✅ 既に AUTO_EXECUTION_ENABLED=false — 追記不要"
  else
    log "false に上書きします..."
    # awk + tmpfile + cat > でinode保持 (sed -i 禁止 / mv はbind-mount破壊)
    _TMP_ENV=$(mktemp "${ENV_FILE}.XXXXXX")
    awk '{
      if ($0 ~ /^AUTO_EXECUTION_ENABLED=/) {
        print "AUTO_EXECUTION_ENABLED=false"
      } else {
        print
      }
    }' "${ENV_FILE}" > "${_TMP_ENV}"
    cat "${_TMP_ENV}" > "${ENV_FILE}"
    rm -f "${_TMP_ENV}"
    log "✅ AUTO_EXECUTION_ENABLED=false に更新しました"
  fi
else
  log "AUTO_EXECUTION_ENABLED は未設定 — 末尾に追記します..."
  # printf で改行保証 (echo >> は前行末に改行がないと連結される可能性あり)
  printf '\nAUTO_EXECUTION_ENABLED=false\n' >> "${ENV_FILE}"
  log "✅ AUTO_EXECUTION_ENABLED=false を追記しました"
fi

log ""
log "--- 追記後の確認 ---"
grep -E "^AUTO_EXECUTION_ENABLED|^REBALANCE_SHADOW_MODE|^POLICY_" "${ENV_FILE}" || log "(該当キーなし)"
log ""

# REBALANCE_SHADOW_MODE が true であることを確認 (v2 では変更しない)
if grep -q '^REBALANCE_SHADOW_MODE=true' "${ENV_FILE}"; then
  log "✅ REBALANCE_SHADOW_MODE=true を確認 (v2 では変更なし)"
else
  log "⚠️  WARN: REBALANCE_SHADOW_MODE=true が見当たりません。現在値:"
  grep '^REBALANCE_SHADOW_MODE=' "${ENV_FILE}" || log "  (未設定)"
fi

human_confirm "PHASE 2 (.env 追記)"

# ──────────────────────────────────────────────────────────────────
# PHASE 2.5: proposals テーブル ALTER (expected_from / expected_to)
# ──────────────────────────────────────────────────────────────────
echo ""
log "══════ PHASE 2.5: proposals テーブル ALTER ══════"

# 現行スキーマ確認
log "--- 現在の proposals カラム一覧 ---"
docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT column_name, data_type, character_maximum_length
   FROM information_schema.columns
   WHERE table_name = 'proposals'
   ORDER BY ordinal_position;" \
  2>/dev/null || log "⚠️  proposals テーブルのカラム取得に失敗"
echo ""

# expected_from / expected_to が既に存在するか確認
_HAS_FROM=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT count(*) FROM information_schema.columns
   WHERE table_name='proposals' AND column_name='expected_from';" \
  2>/dev/null | tr -d ' \n' || echo "0")
_HAS_TO=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT count(*) FROM information_schema.columns
   WHERE table_name='proposals' AND column_name='expected_to';" \
  2>/dev/null | tr -d ' \n' || echo "0")

log "expected_from カラム存在数: ${_HAS_FROM}"
log "expected_to   カラム存在数: ${_HAS_TO}"

if [[ "${_HAS_FROM}" == "1" && "${_HAS_TO}" == "1" ]]; then
  log "✅ expected_from / expected_to は既に存在します — ALTER をスキップ"
else
  log "ALTER TABLE を実行します (IF NOT EXISTS で冪等)..."

  # psql ファイル化 → docker cp → psql -f 方式 ($ 補間回避 §13)
  _SQL_FILE=$(mktemp /tmp/proposals_alter_XXXXXX.sql)
  cat > "${_SQL_FILE}" <<'SQLEOF'
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_from VARCHAR(42);
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_to VARCHAR(42);
SQLEOF

  log "SQL ファイル: ${_SQL_FILE}"
  cat "${_SQL_FILE}"

  # docker cp でコンテナにコピー
  docker cp "${_SQL_FILE}" "${POSTGRES_CONTAINER}:/tmp/proposals_alter.sql"
  rm -f "${_SQL_FILE}"

  # psql -f で実行
  docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -f /tmp/proposals_alter.sql

  # 後始末
  docker exec "${POSTGRES_CONTAINER}" rm -f /tmp/proposals_alter.sql 2>/dev/null || true

  log ""
  log "--- ALTER 後のカラム確認 ---"
  docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
    "SELECT column_name, data_type
     FROM information_schema.columns
     WHERE table_name = 'proposals' AND column_name IN ('expected_from', 'expected_to')
     ORDER BY column_name;"

  # 追加確認
  _HAS_FROM2=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
    "SELECT count(*) FROM information_schema.columns
     WHERE table_name='proposals' AND column_name='expected_from';" \
    2>/dev/null | tr -d ' \n' || echo "0")
  _HAS_TO2=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
    "SELECT count(*) FROM information_schema.columns
     WHERE table_name='proposals' AND column_name='expected_to';" \
    2>/dev/null | tr -d ' \n' || echo "0")

  if [[ "${_HAS_FROM2}" == "1" && "${_HAS_TO2}" == "1" ]]; then
    log "✅ expected_from / expected_to カラムの追加を確認"
  else
    err "カラムが追加されていません (from=${_HAS_FROM2}, to=${_HAS_TO2})"
    exit 1
  fi
fi

human_confirm "PHASE 2.5 (proposals ALTER)"

# ──────────────────────────────────────────────────────────────────
# PHASE 3: デプロイ (backend → frontend)
# ──────────────────────────────────────────────────────────────────
echo ""
log "══════ PHASE 3: デプロイ ══════"

# PHASE 3a: backend deploy (Blue/Green ゼロダウンタイム)
log "--- PHASE 3a: backend-only デプロイ ---"
ALLOW_TESTNET=1 bash "${DEPLOY_SCRIPT}" --backend-only

log ""
log "--- PHASE 3b: frontend-only デプロイ (#476 partner/proposals/page.tsx 変更) ---"
ALLOW_TESTNET=1 bash "${DEPLOY_SCRIPT}" --frontend-only

# frontend 焼き込み確認 (PHASE 3 完了直後)
log ""
log "--- frontend 焼き込み確認 (http:// URL 検出) ---"
_HTTP_COUNT=$(docker exec "${FRONTEND_CONTAINER}" \
  sh -c "find /app/.next/static/chunks -type f | xargs grep -l 'http://77\|http://localhost:8000' 2>/dev/null | wc -l" \
  2>/dev/null || echo "0")
log "Mixed Content 件数: ${_HTTP_COUNT}"
if [[ "${_HTTP_COUNT}" -gt 0 ]]; then
  err "⚠️  ROLLBACK REQUIRED: フロントエンドバンドルに http:// URL が ${_HTTP_COUNT} ファイルで検出"
  err "    → 対処: docker compose -f docker-compose.production.yml build --no-cache frontend → redeploy"
  exit 1
fi
log "✅ Mixed Content なし"

human_confirm "PHASE 3 (デプロイ)"

# ──────────────────────────────────────────────────────────────────
# PHASE 4: デプロイ後検証
# ──────────────────────────────────────────────────────────────────
echo ""
log "══════ PHASE 4: デプロイ後検証 ══════"

# ── 4-1: 環境変数確認 ──
log "--- 4-1: 環境変数確認 ---"

log "  AUTO_EXECUTION_ENABLED : $(grep '^AUTO_EXECUTION_ENABLED=' "${ENV_FILE}" | head -1 | cut -d= -f2- || echo '(未設定)')"
log "  REBALANCE_SHADOW_MODE  : $(grep '^REBALANCE_SHADOW_MODE=' "${ENV_FILE}" | head -1 | cut -d= -f2- || echo '(未設定)')"

# POLICY_ 系を列挙
while IFS='=' read -r _k _v; do
  log "  ${_k}=${_v}"
done < <(grep '^POLICY_' "${ENV_FILE}" 2>/dev/null || true)

# AUTO_EXECUTION_ENABLED=false の厳格確認
_AEE=$(grep '^AUTO_EXECUTION_ENABLED=' "${ENV_FILE}" | head -1 | cut -d= -f2- || echo "")
if [[ "${_AEE}" == "false" ]]; then
  log "✅ AUTO_EXECUTION_ENABLED=false 確認 (F1 kill switch 有効)"
else
  err "AUTO_EXECUTION_ENABLED='${_AEE}' — false が必須です"
  exit 1
fi

# ── 4-2: proposals カラム確認 ──
log ""
log "--- 4-2: proposals.expected_from / expected_to カラム存在確認 ---"
docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT column_name, data_type
   FROM information_schema.columns
   WHERE table_name = 'proposals' AND column_name IN ('expected_from', 'expected_to')
   ORDER BY column_name;"

_COL_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT count(*) FROM information_schema.columns
   WHERE table_name='proposals' AND column_name IN ('expected_from','expected_to');" \
  2>/dev/null | tr -d ' \n' || echo "0")

if [[ "${_COL_COUNT}" == "2" ]]; then
  log "✅ expected_from / expected_to カラム存在確認 (${_COL_COUNT}/2)"
else
  err "proposals に expected_from / expected_to が揃っていません (count=${_COL_COUNT})"
  exit 1
fi

# ── 4-3: ヘルスチェック (内部 nginx 経由) ──
log ""
log "--- 4-3: ヘルスチェック (内部 nginx:${NGINX_PORT}) ---"
_HEALTH_INT=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 \
  "http://localhost:${NGINX_PORT}/health" 2>/dev/null || echo "000")
if [[ "${_HEALTH_INT}" == "200" ]]; then
  log "✅ 内部 /health → ${_HEALTH_INT}"
else
  log "⚠️  内部 /health → ${_HEALTH_INT}"
fi

# ── 4-4: 外形ヘルスチェック ──
log ""
log "--- 4-4: 外形ヘルスチェック (api.ultra-auto-trade.com) ---"
_HEALTH_EXT=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 \
  "https://api.ultra-auto-trade.com/health" 2>/dev/null || echo "000")
if [[ "${_HEALTH_EXT}" == "200" ]]; then
  log "✅ 外形 /health → ${_HEALTH_EXT}"
else
  log "⚠️  外形 /health → ${_HEALTH_EXT} (cloudflared propagation delay の可能性あり)"
fi

# ── 4-5: AI BUY 提案確認 (shadow なので実行されない) ──
log ""
log "--- 4-5: AI BUY 提案確認 (ai_decisions 直近 1h の action=BUY) ---"
_BUY_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -d ultra_autotrade -t -c \
  "SELECT count(*) FROM ai_decisions WHERE action='BUY' AND created_at > now() - interval '1 hour';" \
  2>/dev/null | tr -d ' \n' || echo "unknown")
log "  直近 1h の BUY 提案数: ${_BUY_COUNT}"
if [[ "${_BUY_COUNT}" == "0" || "${_BUY_COUNT}" == "unknown" ]]; then
  log "  ℹ️  直近 1h に BUY 提案なし (次回スケジューラ実行を待つか scheduler_healthy を確認)"
else
  log "✅ AI が BUY 提案あり (REBALANCE_SHADOW_MODE=true のため実行なし、提案のみ)"
fi

# ── 4-6: scheduler_last_error 確認 ──
log ""
log "--- 4-6: scheduler 状態確認 ---"
_HEALTH_JSON=$(curl -sf --max-time 5 "http://localhost:${NGINX_PORT}/health" 2>/dev/null || echo '{}')
_SCHED_HEALTHY=$(echo "${_HEALTH_JSON}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_healthy','unknown'))" \
  2>/dev/null || echo "unknown")
_SCHED_ERR=$(echo "${_HEALTH_JSON}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scheduler_last_error') or '')" \
  2>/dev/null || echo "")
log "  scheduler_healthy=${_SCHED_HEALTHY}"
if [[ -z "${_SCHED_ERR}" ]]; then
  log "✅ scheduler_last_error=なし"
else
  log "⚠️  scheduler_last_error: ${_SCHED_ERR}"
fi

# ── 4-7: frontend 焼き込み念押し確認 ──
log ""
log "--- 4-7: frontend 焼き込み grep (念押し) ---"
_HTTP_COUNT2=$(docker exec "${FRONTEND_CONTAINER}" \
  sh -c "find /app/.next/static/chunks -type f | xargs grep -l 'http://77\|http://localhost:8000' 2>/dev/null | wc -l" \
  2>/dev/null || echo "0")
if [[ "${_HTTP_COUNT2}" -gt 0 ]]; then
  err "⚠️  ROLLBACK REQUIRED: Mixed Content が ${_HTTP_COUNT2} ファイルで検出"
  err "    → 対処: docker compose -f docker-compose.production.yml build --no-cache frontend → redeploy"
  exit 1
fi
log "✅ Mixed Content なし (chunks/ 全ファイル確認)"

# ── 検証サマリ ──
echo ""
log "═══════════════════════════════════════════════════════════════"
log "  PHASE 4 検証サマリ"
log "═══════════════════════════════════════════════════════════════"
log "  AUTO_EXECUTION_ENABLED    : ${_AEE}"
log "  proposals カラム (from/to) : ${_COL_COUNT}/2 存在"
log "  内部 /health               : ${_HEALTH_INT}"
log "  外形 /health               : ${_HEALTH_EXT}"
log "  AI BUY 直近 1h             : ${_BUY_COUNT} 件"
log "  scheduler_healthy          : ${_SCHED_HEALTHY}"
log "  scheduler_last_error       : ${_SCHED_ERR:-なし}"
log "  Mixed Content              : 0 件"
log "═══════════════════════════════════════════════════════════════"
log ""
log "✅ 6/1 partner 実売買デプロイバンドル v2 完了"
log ""
log "⚠️  次のアクション (人間が手動で実施):"
log "   1. partner が提案を承認し proposals.status が pending → approved に遷移するか確認"
log "   2. submit_partner_tx API で tx を送信し expected_from/expected_to 照合が通るか確認"
log "   3. REBALANCE_SHADOW_MODE=false への切替は Go条件5点実機確認後の別手動"

human_confirm "PHASE 4 (検証)"

log "デプロイバンドル v2 完了。お疲れさまでした。"
