#!/bin/bash
set -euo pipefail

# ============================================================
# deploy_6_1_bundle.sh — 6/1 production deploy bundle
#
# 実行場所: 本番 Hetzner VPS (77.42.46.155) / ultra ユーザー
#   ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
#   cd /opt/ultra-autotrade
#   bash scripts/deploy_6_1_bundle.sh
#
# 処理順:
#   PHASE 0 (READ-ONLY)  プレフライト確認・diff 表示 → 人間確認 (y/N)
#   PHASE 1 (WRITE)      git pull → stash 確認 → stash drop
#   PHASE 2 (WRITE)      .env.production 編集 (awk atomic) → diff → 人間確認 (y/N)
#   PHASE 3 (WRITE)      deploy_production.sh --backend-only (Blue/Green)
#   PHASE 4 (READ)       os.getenv 検証 / ValidationError チェック / 焼き込み grep
#
# ⚠️  本 deploy は backend のみ (--backend-only)。
#     #466 (frontend itp-reauth) は frontend 変更のため本スクリプトでは反映されない。
#     #466 は別途 deploy_production.sh --frontend-only で個別デプロイすること。
#
# ============================================================

for _arg in "$@"; do
  if [[ "$_arg" == "-v" || "$_arg" == "--volumes" ]]; then
    echo "❌ ERROR: -v / --volumes フラグは禁止です。DBボリュームが削除されます。"
    exit 1
  fi
done

# ───────────────────────────────────────────────
# 定数
# 本番 VPS リポジトリルート: /opt/ultra-autotrade/ (main/ サブディレクトリなし)
# ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.production.yml"
ENV_FILE="${PROJECT_ROOT}/.env.production"
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy_production.sh"
STASH_NAME="keep-staging-green-upstream-20260531"

# 6/1 bundle で書き込む 4 キーと期待値 (HF_FLOOR は default 1.5 のまま env に書かない)
KEY_REBALANCE_SHADOW="REBALANCE_SHADOW_MODE";          VAL_REBALANCE_SHADOW="true"
KEY_MAX_POS="POLICY_MAX_POSITION_USD";                 VAL_MAX_POS="1000"
KEY_DAILY_VEL="POLICY_DAILY_VELOCITY_CAP_USD";         VAL_DAILY_VEL="2000"
KEY_HOURLY_VEL="POLICY_HOURLY_VELOCITY_CAP_USD";       VAL_HOURLY_VEL="1000"

# ───────────────────────────────────────────────
# ヘルパー
# ───────────────────────────────────────────────
log()  { echo "[6-1-bundle] $*"; }
err()  { echo "[6-1-bundle] ERROR: $*" >&2; }

sep() {
  echo ""
  echo "══════════════════════════════════════════════════════════"
  printf "  %s\n" "$*"
  echo "══════════════════════════════════════════════════════════"
}

confirm_or_abort() {
  local prompt="$1"
  echo ""
  echo ">>> ${prompt}"
  printf "    続行するには 'y' を入力 (それ以外でアボート): "
  read -r _ans
  if [[ "${_ans}" != "y" && "${_ans}" != "Y" ]]; then
    err "ユーザーによりアボートされました。"
    exit 1
  fi
}

# .env から指定キーの現在値を返す (存在しなければ空文字)
env_current() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || echo ""
}

# docker compose コマンドを解決
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

# ═══════════════════════════════════════════════════════════
# PHASE 0: READ-ONLY プレフライト (書き込みなし)
# ═══════════════════════════════════════════════════════════
sep "PHASE 0: READ-ONLY プレフライト"

cd "${PROJECT_ROOT}"
log "project root: ${PROJECT_ROOT}"

# --- 前提ファイルチェック ---
if [[ ! -f "${ENV_FILE}" ]]; then
  err "${ENV_FILE} が見つかりません"
  exit 1
fi
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  err "${COMPOSE_FILE} が見つかりません"
  exit 1
fi
if [[ ! -x "${DEPLOY_SCRIPT}" ]]; then
  err "${DEPLOY_SCRIPT} が見つかりません (または実行権限なし)"
  exit 1
fi

# --- .env.production パーミッション確認 ---
_ENV_PERM=$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%OLp' "${ENV_FILE}" 2>/dev/null || echo "unknown")
if [[ "${_ENV_PERM}" != "600" ]]; then
  err "${ENV_FILE} のパーミッション: ${_ENV_PERM} (600 必須)"
  err "  修正: chmod 600 ${ENV_FILE}"
  exit 1
fi
log "✅ .env.production パーミッション: ${_ENV_PERM}"

# --- active backend を動的解決 ---
BACKEND=$(docker ps --format '{{.Names}}' | grep -E 'backend-(blue|green)-production' | head -1 || echo "")
if [[ -z "${BACKEND}" ]]; then
  err "active backend コンテナが見つかりません (backend-(blue|green)-production が起動していない)"
  exit 1
fi
log "active backend コンテナ (deploy 前): ${BACKEND}"

DC=$(resolve_dc)
log "docker compose コマンド: ${DC}"

# --- git 状態確認 ---
log "git status:"
git status --short || true
log "現在の HEAD:"
git log --oneline -1

# --- stash 確認 ---
log "git stash list:"
git stash list 2>/dev/null || true
STASH_LINE=$(git stash list 2>/dev/null | grep "${STASH_NAME}" | head -1 || echo "")
if [[ -z "${STASH_LINE}" ]]; then
  log "⚠️  stash '${STASH_NAME}' が見つかりません (既に drop 済みまたは存在しない)"
  STASH_FOUND=false
else
  STASH_REF=$(echo "${STASH_LINE}" | awk '{print $1}' | tr -d ':')
  log "✅ stash 確認: ${STASH_REF} → ${STASH_NAME}"
  STASH_FOUND=true
fi

# --- .env.production 現状 md5 ---
MD5_BEFORE=$(md5sum "${ENV_FILE}" | awk '{print $1}')
log ".env.production 現在の md5: ${MD5_BEFORE}"

# --- 変更予定を表示 ---
echo ""
log "--- .env.production 変更予定 (現在値 → 書き込み予定値) ---"
for pair in \
  "${KEY_REBALANCE_SHADOW}=${VAL_REBALANCE_SHADOW}" \
  "${KEY_MAX_POS}=${VAL_MAX_POS}" \
  "${KEY_DAILY_VEL}=${VAL_DAILY_VEL}" \
  "${KEY_HOURLY_VEL}=${VAL_HOURLY_VEL}"; do
  _k="${pair%%=*}"
  _want="${pair#*=}"
  _cur=$(env_current "${_k}")
  if [[ -z "${_cur}" ]]; then
    log "  NEW   ${_k}=(未設定) → ${_want}"
  elif [[ "${_cur}" == "${_want}" ]]; then
    log "  SAME  ${_k}=${_cur}  (変更なし)"
  else
    log "  DIFF  ${_k}: '${_cur}' → '${_want}'"
  fi
done
echo ""

confirm_or_abort "PHASE 0 完了。確認して PHASE 1 (git pull + stash drop) へ進みますか？"

# ═══════════════════════════════════════════════════════════
# PHASE 1: git pull + stash drop
# 順序: pull → 確認 → drop  (引数なし drop 禁止 / 名前で特定)
# ═══════════════════════════════════════════════════════════
sep "PHASE 1: git pull + stash drop"

# 1a. git pull origin main
log "git pull origin main ..."
git pull origin main

log "pull 後 HEAD:"
git log --oneline -1

# 1b. pull 後に stash を再確認してから drop
if "${STASH_FOUND}"; then
  log "pull 後 stash list:"
  git stash list 2>/dev/null || true
  STASH_LINE_POST=$(git stash list 2>/dev/null | grep "${STASH_NAME}" | head -1 || echo "")
  if [[ -z "${STASH_LINE_POST}" ]]; then
    log "⚠️  pull 後に stash '${STASH_NAME}' が見つかりません — stash drop をスキップ"
  else
    STASH_REF_POST=$(echo "${STASH_LINE_POST}" | awk '{print $1}' | tr -d ':')
    log "stash drop 対象確認: ${STASH_REF_POST} (${STASH_NAME})"
    git stash drop "${STASH_REF_POST}"
    log "✅ stash drop 完了: ${STASH_REF_POST}"
  fi
else
  log "stash '${STASH_NAME}' が最初から存在しないため drop をスキップ"
fi

log "drop 後 stash list:"
git stash list 2>/dev/null || true

# ═══════════════════════════════════════════════════════════
# PHASE 2: .env.production 編集 (awk atomic)
# append(>>) 禁止 / sed -i 禁止 / mv 禁止
# → awk + mktemp + cat > でinode保持 (bind-mount 対応)
# ═══════════════════════════════════════════════════════════
sep "PHASE 2: .env.production 編集 (awk atomic)"

# 2a. バックアップ cp
_STAMP=$(date +%Y%m%d_%H%M%S)
ENV_BACKUP="${ENV_FILE}.bak.${_STAMP}"
cp "${ENV_FILE}" "${ENV_BACKUP}"
log "バックアップ作成: ${ENV_BACKUP}"

# 2b. md5 before (書き込み直前)
MD5_BEFORE_WRITE=$(md5sum "${ENV_FILE}" | awk '{print $1}')
log "md5_before_write: ${MD5_BEFORE_WRITE}"

# 2c. awk 1 パスで 4 キーを置換/追記
# - 既存キー行を置換 (seen フラグ)
# - END で未出現キーを末尾追記
_TMP=$(mktemp "${ENV_FILE}.XXXXXX")

awk \
  -v k1="${KEY_REBALANCE_SHADOW}" -v v1="${VAL_REBALANCE_SHADOW}" \
  -v k2="${KEY_MAX_POS}"          -v v2="${VAL_MAX_POS}" \
  -v k3="${KEY_DAILY_VEL}"        -v v3="${VAL_DAILY_VEL}" \
  -v k4="${KEY_HOURLY_VEL}"       -v v4="${VAL_HOURLY_VEL}" \
'
BEGIN {
  keys[1]=k1; vals[1]=v1
  keys[2]=k2; vals[2]=v2
  keys[3]=k3; vals[3]=v3
  keys[4]=k4; vals[4]=v4
  for (i=1; i<=4; i++) seen[keys[i]] = 0
}
{
  matched = 0
  for (i=1; i<=4; i++) {
    if ($0 ~ ("^" keys[i] "=")) {
      print keys[i] "=" vals[i]
      seen[keys[i]] = 1
      matched = 1
      break
    }
  }
  if (!matched) print
}
END {
  for (i=1; i<=4; i++) {
    if (!seen[keys[i]]) {
      print keys[i] "=" vals[i]
    }
  }
}
' "${ENV_FILE}" > "${_TMP}"

# inode 保持: cat > (mv は bind-mount を壊すため禁止)
cat "${_TMP}" > "${ENV_FILE}"
rm -f "${_TMP}"

# 2d. md5 after 記録
MD5_AFTER_WRITE=$(md5sum "${ENV_FILE}" | awk '{print $1}')
log "md5_after_write:  ${MD5_AFTER_WRITE}"
if [[ "${MD5_BEFORE_WRITE}" == "${MD5_AFTER_WRITE}" ]]; then
  log "  (md5 変化なし — 全キーが既に期待値と同じ)"
else
  log "  ✅ md5 変化あり"
fi

# 2e. diff 表示 (バックアップ vs 現在)
echo ""
log "--- .env.production diff (backup vs 現在) ---"
diff "${ENV_BACKUP}" "${ENV_FILE}" || true
echo ""

# 2f. 4 キーの現在値を表示して確認
log "--- 変更後の 4 キー確認 ---"
_phase2_ok=true
for pair in \
  "${KEY_REBALANCE_SHADOW}=${VAL_REBALANCE_SHADOW}" \
  "${KEY_MAX_POS}=${VAL_MAX_POS}" \
  "${KEY_DAILY_VEL}=${VAL_DAILY_VEL}" \
  "${KEY_HOURLY_VEL}=${VAL_HOURLY_VEL}"; do
  _k="${pair%%=*}"
  _want="${pair#*=}"
  _cur=$(env_current "${_k}")
  if [[ "${_cur}" == "${_want}" ]]; then
    log "  ✅ ${_k}=${_cur}"
  else
    log "  ❌ ${_k}=${_cur}  (期待値: ${_want})"
    _phase2_ok=false
  fi
done
if ! "${_phase2_ok}"; then
  err "期待値と不一致のキーがあります。アボートします。"
  err "  バックアップから復元: cp ${ENV_BACKUP} ${ENV_FILE}"
  exit 1
fi
echo ""

confirm_or_abort "PHASE 2 .env 編集完了。diff を確認して PHASE 3 (deploy) へ進みますか？"

# ═══════════════════════════════════════════════════════════
# PHASE 3: deploy (--backend-only, Blue/Green ゼロダウンタイム)
# deploy_production.sh が内部で
#   docker compose -f docker-compose.production.yml \
#     --env-file .env.production \
#     build / up / stop
# を実行する
# ═══════════════════════════════════════════════════════════
sep "PHASE 3: deploy (--backend-only)"

log "${DEPLOY_SCRIPT} --backend-only を実行します"
log "  (deploy_production.sh 内部で --env-file ${ENV_FILE} を使用)"

bash "${DEPLOY_SCRIPT}" --backend-only

log "✅ PHASE 3 deploy 完了"

# ═══════════════════════════════════════════════════════════
# PHASE 4: deploy 後検証
# ═══════════════════════════════════════════════════════════
sep "PHASE 4: deploy 後検証"

# deploy 後に active backend を再解決 (Blue/Green 切替後は変わっている)
BACKEND_POST=$(docker ps --format '{{.Names}}' | grep -E 'backend-(blue|green)-production' | head -1 || echo "")
if [[ -z "${BACKEND_POST}" ]]; then
  err "deploy 後の active backend コンテナが見つかりません"
  exit 1
fi
log "deploy 後 active backend: ${BACKEND_POST}"
if [[ "${BACKEND}" != "${BACKEND_POST}" ]]; then
  log "✅ Blue/Green 切替確認: ${BACKEND} → ${BACKEND_POST}"
else
  log "  backend コンテナ名変化なし (Blue/Green 両 container が同名の場合は正常)"
fi

# 4a. os.getenv で POLICY_ 3キー + REBALANCE_SHADOW_MODE を確認
# 秘密値 (DATABASE_URL 等) は出力しない
log "=== os.getenv 検証 (${BACKEND_POST}) ==="
docker exec "${BACKEND_POST}" python3 - <<'PYEOF'
import os, sys

checks = [
    ("REBALANCE_SHADOW_MODE",          "true"),
    ("POLICY_MAX_POSITION_USD",        "1000"),
    ("POLICY_DAILY_VELOCITY_CAP_USD",  "2000"),
    ("POLICY_HOURLY_VELOCITY_CAP_USD", "1000"),
]
failed = []
for key, expected in checks:
    actual = os.getenv(key, "(未設定)")
    if actual == expected:
        print(f"  ✅ {key}={actual}")
    else:
        print(f"  ❌ {key}={actual!r}  (期待値: {expected!r})")
        failed.append(key)

print()
if failed:
    print(f"FAIL: {len(failed)} キーが期待値と不一致: {failed}", file=sys.stderr)
    sys.exit(1)
else:
    print("✅ 全 4 キー os.getenv 確認 OK")
PYEOF

# 4b. rebalance_check_loop 起動確認 (#471 cap 効果)
# ValidationError / RuntimeError が出ていないことを確認
log "=== rebalance_check_loop 起動確認 (${BACKEND_POST}) ==="
sleep 8
RECENT_LOGS=$(docker logs "${BACKEND_POST}" 2>&1 | tail -200)

if echo "${RECENT_LOGS}" | grep -q "Starting rebalance check loop"; then
  log "✅ rebalance_check_loop 起動ログ確認"
else
  log "⚠️  rebalance_check_loop 起動ログが見つかりません (まだ起動中かもしれません)"
fi

if echo "${RECENT_LOGS}" | grep -qiE "ValidationError|RuntimeError.*rebalance|rebalance.*Error"; then
  err "❌ rebalance_check_loop でエラーが検出されました:"
  echo "${RECENT_LOGS}" | grep -iE "ValidationError|RuntimeError.*rebalance|rebalance.*Error" | tail -10
  log "   → .env.production の REBALANCE_* / POLICY_* キーの値を確認してください"
  log "   → ロールバック: cp ${ENV_BACKUP} ${ENV_FILE} && bash ${DEPLOY_SCRIPT} --backend-only"
else
  log "✅ ValidationError / RuntimeError なし (${BACKEND_POST})"
fi

# 4c. 焼き込み grep (コンテナ内コードに POLICY_ / REBALANCE_SHADOW_MODE の参照があるか)
# PR #471 で POLICY_ キーが追加されていることを確認
log "=== 焼き込み grep (${BACKEND_POST} 内 /app/backend/app/) ==="
GREP_RESULT=$(docker exec "${BACKEND_POST}" \
  grep -r \
    -e "POLICY_MAX_POSITION_USD" \
    -e "POLICY_DAILY_VELOCITY_CAP_USD" \
    -e "POLICY_HOURLY_VELOCITY_CAP_USD" \
    -e "REBALANCE_SHADOW_MODE" \
    /app/app/ \
    --include="*.py" -l 2>/dev/null || echo "")

if [[ -n "${GREP_RESULT}" ]]; then
  log "✅ 焼き込み grep: 以下のファイルで参照確認"
  echo "${GREP_RESULT}" | sed 's/^/    /'
else
  log "⚠️  POLICY_ / REBALANCE_SHADOW_MODE の参照がコンテナ内コードに見つかりません"
  log "   PR #471 が deploy 済みであれば調査が必要。未 deploy の場合は正常 (env は先行設定済み)"
fi

# ───────────────────────────────────────────────
# 最終サマリ
# ───────────────────────────────────────────────
sep "6/1 deploy bundle 完了サマリ"
log "  stash:          ${STASH_NAME}"
log "  .env backup:    ${ENV_BACKUP}"
log "  .env md5:       ${MD5_BEFORE} → ${MD5_AFTER_WRITE}"
log "  deploy:         --backend-only (Blue/Green)"
log "  backend_before: ${BACKEND}"
log "  backend_after:  ${BACKEND_POST}"
log ""
log "✅ 6/1 deploy bundle 完了"
