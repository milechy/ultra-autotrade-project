#!/usr/bin/env bash
# scripts/seed_staging_admin.sh — staging admin user 投入/更新スクリプト
#
# staging DB に hkobayashi@mooores.com (role=admin) を UPSERT する。
# staging 復旧後に毎回実行して admin user を永続化する。
#
# 使用法:
#   /opt/ultra-autotrade/scripts/seed_staging_admin.sh
#   ADMIN_PASSWORD=xxx /opt/ultra-autotrade/scripts/seed_staging_admin.sh
#   ADMIN_EMAIL=other@example.com ADMIN_PASSWORD=xxx ./scripts/seed_staging_admin.sh
#
# 環境変数:
#   POSTGRES_CONTAINER  (default: 自動検出 — staging postgres コンテナ)
#   BACKEND_CONTAINER   (default: 自動検出 — nginx upstream の active 側 backend)
#   DB_USER             (default: ultra)
#   DB_NAME             (default: ultra_autotrade_staging)
#   ADMIN_EMAIL         (default: hkobayashi@mooores.com)
#   ADMIN_PASSWORD      (未設定時は対話入力)
#
# 禁止: production コンテナへの実行。CONTAINER 名に "staging" を含まない場合は exit 1。

set -euo pipefail

DB_USER="${DB_USER:-ultra}"
DB_NAME="${DB_NAME:-ultra_autotrade_staging}"
ADMIN_EMAIL="${ADMIN_EMAIL:-hkobayashi@mooores.com}"
ADMIN_ROLE="admin"

# ── postgres コンテナ動的検出 ─────────────────────────────────────────────────
if [[ -z "${POSTGRES_CONTAINER:-}" ]]; then
  POSTGRES_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
    | grep postgres | grep staging | head -1 || true)
fi
CONTAINER="${POSTGRES_CONTAINER:-}"
if [[ -z "${CONTAINER}" ]]; then
  echo "ERROR: staging postgres コンテナが見つかりません。docker ps | grep postgres を確認してください。" >&2
  exit 1
fi

# ── backend コンテナ動的検出 (nginx upstream.conf の active 側を参照) ──────────
if [[ -z "${BACKEND_CONTAINER:-}" ]]; then
  NGINX_C=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
    | grep nginx | grep staging | head -1 || true)
  ACTIVE_ALIAS=""
  if [[ -n "${NGINX_C}" ]]; then
    ACTIVE_ALIAS=$(docker exec "${NGINX_C}" cat /etc/nginx/conf.d/upstream.conf 2>/dev/null \
      | grep -oP 'backend-\w+' | head -1 || true)
  fi
  if [[ -n "${ACTIVE_ALIAS}" ]]; then
    BACKEND_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
      | grep "${ACTIVE_ALIAS}" | grep staging | head -1 || true)
  fi
  # フォールバック: nginx が取れなければ任意の running staging backend
  if [[ -z "${BACKEND_CONTAINER:-}" ]]; then
    BACKEND_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
      | grep backend | grep staging | head -1 || true)
  fi
fi
if [[ -z "${BACKEND_CONTAINER:-}" ]]; then
  echo "ERROR: staging backend コンテナが見つかりません。docker ps | grep backend を確認してください。" >&2
  exit 1
fi

# ── Safety: staging コンテナのみ許可 ─────────────────────────────────────────
if [[ "${CONTAINER}" != *"staging"* ]]; then
  echo "ERROR: staging コンテナのみ許可。CONTAINER=${CONTAINER} は production 系のため中断します。" >&2
  exit 1
fi

echo "[seed_staging_admin] postgres コンテナ: ${CONTAINER}"
echo "[seed_staging_admin] backend コンテナ : ${BACKEND_CONTAINER} (nginx active 側)"
echo "[seed_staging_admin] DB               : ${DB_NAME}"
echo "[seed_staging_admin] Admin email      : ${ADMIN_EMAIL}"

# ── パスワード取得 ────────────────────────────────────────────────────────────
if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
  echo -n "[seed_staging_admin] ADMIN_PASSWORD を入力してください (非表示): "
  read -rs ADMIN_PASSWORD
  echo ""
fi

if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
  echo "ERROR: パスワードは 8 文字以上必要です。" >&2
  exit 1
fi

# ── bcrypt hash 生成 (env var 経由で渡す / passlib → bcrypt の順でフォールバック) ──
echo "[seed_staging_admin] bcrypt hash 生成中..."
HASHED=$(docker exec -e "SEED_PWD=${ADMIN_PASSWORD}" "${BACKEND_CONTAINER}" \
  python3 -c "
import os, sys
pwd = os.environ['SEED_PWD']
try:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')
    print(ctx.hash(pwd))
except Exception as e1:
    try:
        import bcrypt
        print(bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt(12)).decode())
    except Exception as e2:
        print(f'FAIL passlib={e1} bcrypt={e2}', file=sys.stderr)
        sys.exit(1)
" 2>&1 || true)

if [[ "${HASHED:0:4}" != '$2b$' ]] && [[ "${HASHED:0:4}" != '$2a$' ]]; then
  echo "ERROR: bcrypt hash 生成失敗。実際のエラー: ${HASHED}" >&2
  exit 1
fi
echo "[seed_staging_admin] bcrypt hash 生成完了"

# ── users テーブル schema 確認 ────────────────────────────────────────────────
echo ""
echo "[seed_staging_admin] users テーブル schema:"
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c \
  "SELECT column_name, data_type, is_nullable, column_default
   FROM information_schema.columns
   WHERE table_name = 'users'
   ORDER BY ordinal_position;" 2>/dev/null || true
echo ""

# ── 既存ユーザー確認 → UPDATE or INSERT ──────────────────────────────────────
EXISTING_ID=$(docker exec "${CONTAINER}" \
  psql -U "${DB_USER}" -d "${DB_NAME}" -t -A -c \
  "SELECT id FROM users WHERE email = '${ADMIN_EMAIL}';" 2>/dev/null | tr -d '[:space:]' || true)

if [[ -n "${EXISTING_ID}" ]]; then
  echo "[seed_staging_admin] 既存ユーザー検出 (id=${EXISTING_ID}) — hashed_password / role を UPDATE します"
  docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c \
    "UPDATE users
     SET hashed_password = '${HASHED}',
         role            = '${ADMIN_ROLE}',
         tier            = 'GENERAL',
         is_active       = true,
         updated_at      = NOW()
     WHERE email = '${ADMIN_EMAIL}';"
  echo "[seed_staging_admin] UPDATE 完了"
else
  echo "[seed_staging_admin] ユーザー未存在 — INSERT します"
  # users テーブルの NOT NULL 必須カラムのみ指定。他はDB default に委ねる。
  docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c \
    "INSERT INTO users (email, hashed_password, role, tier, is_active, created_at, updated_at)
     VALUES ('${ADMIN_EMAIL}', '${HASHED}', '${ADMIN_ROLE}', 'GENERAL', true, NOW(), NOW());" \
  || {
    echo ""
    echo "ERROR: INSERT 失敗。NOT NULL エラーの場合は上記 schema を確認し、" >&2
    echo "       不足カラムを追加してください (例: tier, execution_policy 等)。" >&2
    exit 1
  }
  echo "[seed_staging_admin] INSERT 完了"
fi

# ── 確認 ─────────────────────────────────────────────────────────────────────
echo ""
echo "[seed_staging_admin] 結果確認:"
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c \
  "SELECT id, email, role, hashed_password IS NOT NULL AS has_pwd, is_active, created_at
   FROM users WHERE email = '${ADMIN_EMAIL}';"

echo ""
echo "[seed_staging_admin] 完了: ${ADMIN_EMAIL} を role=${ADMIN_ROLE} で ${DB_NAME} に投入しました。"
echo "[seed_staging_admin] ブラウザで https://staging.ultra-auto-trade.com にログインして動作確認してください。"
