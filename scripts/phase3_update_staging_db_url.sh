#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# phase3_update_staging_db_url.sh
#
# Phase 3: .env.staging の DATABASE_URL を ultra_autotrade_staging へ更新する。
#
# 実行前に staging 環境の現状を確認し、ultra_autotrade_staging DB が存在しない
# 場合はバックアップ・sed を実行せず人間に報告して終了する。
#
# 使い方:
#   bash scripts/phase3_update_staging_db_url.sh
#   bash scripts/phase3_update_staging_db_url.sh --dry-run  # sed を実行しない
#
# 前提:
#   - Hetzner VPS 上で実行する（staging コンテナが起動していること）
#   - .env.staging が同ディレクトリに存在すること
#
# 終了コード:
#   0: 完了（dry-run 含む）
#   1: 事前確認失敗（DB 不在 / ファイル不在 / 不整合）
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${PROJECT_ROOT}/.env.staging"
BACKEND_CONTAINER="ultra-autotrade-backend-staging-new"
POSTGRES_CONTAINER="ultra-autotrade-postgres-staging-new"
TARGET_DB="ultra_autotrade_staging"

DRY_RUN=false
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    *) echo "不明なオプション: ${arg}"; exit 1 ;;
  esac
done

log()  { echo "[phase3] $*"; }
warn() { echo "[phase3] ⚠️  WARNING: $*"; }
err()  { echo "[phase3] ❌ ERROR: $*" >&2; }

# マスク: postgresql://user:password@host/db → postgresql://user:***@host/db
mask_db_url() {
  local url="$1"
  # postgres://user:password@host:port/db 形式のパスワード部分を *** に置換
  echo "${url}" | sed -E 's|(:\/\/[^:]+:)[^@]+(@)|\1***\2|'
}

echo "=== Phase 3: staging DATABASE_URL 更新 ==="
[[ "${DRY_RUN}" == "true" ]] && log "dry-run モード（実際の変更はしません）"

# ---------------------------------------------------------------------------
# 前提チェック: .env.staging の存在
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  err ".env.staging が見つかりません: ${ENV_FILE}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: 現在の DATABASE_URL を確認（コンテナ内の実値）
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 1: コンテナ内 DATABASE_URL の確認 ---"

CONTAINER_DB_URL=""
if docker ps --format "{{.Names}}" | grep -qx "${BACKEND_CONTAINER}"; then
  RAW_URL="$(docker exec "${BACKEND_CONTAINER}" env 2>/dev/null \
    | grep '^DATABASE_URL=' | head -n 1 | sed 's/^DATABASE_URL=//')"
  CONTAINER_DB_URL="${RAW_URL}"
  log "コンテナ DATABASE_URL: $(mask_db_url "${CONTAINER_DB_URL}")"
else
  warn "バックエンドコンテナ (${BACKEND_CONTAINER}) が起動していません"
  warn "コンテナ内の値を確認できないため、.env.staging の値で続行します"
fi

# .env.staging から現在の値を取得
FILE_DB_URL="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -n 1 | sed 's/^DATABASE_URL=//')"
log ".env.staging DATABASE_URL: $(mask_db_url "${FILE_DB_URL}")"

# すでに TARGET_DB に変更済みか確認
if echo "${FILE_DB_URL}" | grep -q "${TARGET_DB}"; then
  log "✅ .env.staging は既に ${TARGET_DB} を使用しています。変更不要です。"
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 2: ultra_autotrade_staging DB の存在確認
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 2: ${TARGET_DB} DB の存在確認 ---"

if ! docker ps --format "{{.Names}}" | grep -qx "${POSTGRES_CONTAINER}"; then
  err "PostgreSQL コンテナ (${POSTGRES_CONTAINER}) が起動していません"
  err "staging 環境を起動してから再実行してください"
  exit 1
fi

DB_LIST="$(docker exec "${POSTGRES_CONTAINER}" psql -U ultra -l 2>/dev/null || echo "")"
log "DB 一覧:"
echo "${DB_LIST}" | grep -E "^\s*(Name|ultra|postgres|template)" | head -20 || true

if echo "${DB_LIST}" | grep -q "${TARGET_DB}"; then
  log "✅ ${TARGET_DB} が存在します。DATABASE_URL 更新を続行します。"
else
  err "${TARGET_DB} DB が存在しません！"
  err ""
  err "【次のアクション（人間が実施）】"
  err "  1. PostgreSQL コンテナで DB を作成:"
  err "     docker exec -it ${POSTGRES_CONTAINER} psql -U ultra -c \"CREATE DATABASE ${TARGET_DB};\""
  err "  2. DB 作成後に本スクリプトを再実行してください"
  err ""
  err ".env.staging の DATABASE_URL 修正を保留します。"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: .env.staging のバックアップ
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 3: .env.staging バックアップ ---"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${ENV_FILE}.bak_${TIMESTAMP}"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] バックアップスキップ: ${BACKUP_FILE}"
else
  cp "${ENV_FILE}" "${BACKUP_FILE}"
  log "バックアップ作成: ${BACKUP_FILE}"
fi

# ---------------------------------------------------------------------------
# Step 4: DATABASE_URL を sed で更新
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 4: DATABASE_URL 更新 ---"

# 現在の DB 名を取得（URL 末尾の /dbname 部分）
CURRENT_DB_NAME="$(echo "${FILE_DB_URL}" | sed -E 's|.*/([^?]+)(\?.*)?$|\1|')"
log "置換: ${CURRENT_DB_NAME} → ${TARGET_DB}"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] sed をスキップ"
  UPDATED_URL="$(echo "${FILE_DB_URL}" | sed "s|/${CURRENT_DB_NAME}|/${TARGET_DB}|g")"
  log "変更後 DATABASE_URL (予測): $(mask_db_url "${UPDATED_URL}")"
else
  # macOS (BSD sed) と Linux (GNU sed) の両方に対応
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s|DATABASE_URL=.*/${CURRENT_DB_NAME}|DATABASE_URL=$(echo "${FILE_DB_URL}" | sed "s|/${CURRENT_DB_NAME}|/${TARGET_DB}|g")|" "${ENV_FILE}"
  else
    # macOS: -i '' が必要
    sed -i '' "s|/${CURRENT_DB_NAME}\([^/]\)|/${TARGET_DB}\1|g" "${ENV_FILE}"
  fi
  log "sed 実行完了"
fi

# ---------------------------------------------------------------------------
# Step 5: diff 確認（パスワードマスク付き）
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 5: 変更差分の確認 ---"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] diff スキップ"
else
  # パスワード部分をマスクした diff
  MASKED_BACKUP="$(sed -E 's|(DATABASE_URL=.*://[^:]+:)[^@]+(@)|\1***\2|g' "${BACKUP_FILE}")"
  MASKED_CURRENT="$(sed -E 's|(DATABASE_URL=.*://[^:]+:)[^@]+(@)|\1***\2|g' "${ENV_FILE}")"

  DIFF_RESULT="$(diff <(echo "${MASKED_BACKUP}") <(echo "${MASKED_CURRENT}") || true)"
  if [[ -z "${DIFF_RESULT}" ]]; then
    warn "差分なし — sed が正常に動作していない可能性があります"
    warn "バックアップと比較して手動確認してください: ${BACKUP_FILE}"
  else
    echo "${DIFF_RESULT}"
  fi
fi

# ---------------------------------------------------------------------------
# Step 6: 最終値確認（マスク付き）
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 6: 最終値確認 ---"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "[dry-run] 確認スキップ"
else
  FINAL_URL="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -n 1 | sed 's/^DATABASE_URL=//')"
  log ".env.staging DATABASE_URL (最終): $(mask_db_url "${FINAL_URL}")"

  if echo "${FINAL_URL}" | grep -q "${TARGET_DB}"; then
    log "✅ DATABASE_URL が ${TARGET_DB} に更新されました"
  else
    err "DATABASE_URL に ${TARGET_DB} が含まれていません。sed が失敗した可能性があります。"
    err "バックアップ: ${BACKUP_FILE}"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# 完了
# ---------------------------------------------------------------------------
echo ""
echo "=== Phase 3 完了 ==="
if [[ "${DRY_RUN}" == "true" ]]; then
  log "dry-run 終了。--dry-run を外して再実行すると実際に更新されます。"
else
  log "次のステップ:"
  log "  1. docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --no-deps backend"
  log "  2. docker exec ${BACKEND_CONTAINER} env | grep DATABASE_URL でコンテナ内の値を確認"
  log "  3. curl http://localhost:8001/health でバックエンドヘルスチェック"
fi
