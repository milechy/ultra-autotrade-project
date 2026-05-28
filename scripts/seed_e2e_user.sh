#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/seed_e2e_user.sh
#
# E2E 専用 testnet user を staging DB に冪等 seed する。
#
# 背景:
#   yamamoto-partner-flow.spec.ts (TC1-TC7) は credentials 未設定で 14 fail
#   する状況。e2e 専用の固定 user (id=999998) を staging DB に常駐させて、
#   playwright の E2E_PARTNER_EMAIL/PASSWORD と接続できるようにする。
#
# 設計確定済 (親 Lane 承認):
#   - id          = 999998 (山本さん user_id=11 と絶対衝突しない値)
#   - email       = e2e-partner@ultra-autotrade.local
#   - role        = partner
#   - execution_policy = require_approval (TC4 承認フロー検証のため)
#   - tier        = GENERAL (仕様書準拠 / 既存 PARTNER_MOCK_USER と整合)
#                   ※ 現 InvestmentTier enum 標準値は LOWER だが users テーブル
#                     には tier CHECK 制約は無いので挿入可。
#   - wallet      = testnet 専用 (env から注入、mainnet 鍵不使用)
#   - password    = bcrypt ハッシュを env から注入 (リテラル禁止)
#
# 二重ガード:
#   1. --env=production を受け付けない (即 exit 2)
#   2. DATABASE_URL から取り出した DB 名が "*staging*" を含むか再確認
#      (=production DB を staging だと誤指定した場合の防御線)
#
# Usage:
#   E2E_PARTNER_PASSWORD_HASH='$2b$12$...' \
#   E2E_PARTNER_WALLET_ADDRESS='0xabc...' \
#   DATABASE_URL='postgresql://...staging-new...' \
#     bash scripts/seed_e2e_user.sh --env=staging
#
# 終了コード:
#   0 — seed 成功
#   1 — psql 実行失敗 (DB 接続不可 / SQL エラー)
#   2 — 設定エラー (--env=production 拒否 / DATABASE_URL 未設定 /
#        E2E_PARTNER_* env 未設定 / DB 名が staging を含まない)
#
# 参考:
#   - 山本さん user_id=11 への影響ゼロ (id=999998 は山本と絶対衝突しない)
#   - production DB への書き込みは一切しない
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
${SCRIPT_NAME} — E2E 専用 testnet user (id=999998) を staging DB に冪等 seed

Usage:
  ${SCRIPT_NAME} --env=staging
  ${SCRIPT_NAME} --help

Required environment variables:
  DATABASE_URL                 staging DB URL (postgresql://...)
                               DB 名に "staging" を含むこと
  E2E_PARTNER_PASSWORD_HASH    bcrypt ハッシュ (例: \$2b\$12\$...)
  E2E_PARTNER_WALLET_ADDRESS   testnet ウォレット address (0x...)

Optional environment variables:
  E2E_PARTNER_EMAIL            既定: e2e-partner@ultra-autotrade.local

Exit codes:
  0  seed 成功
  1  DB 接続失敗 / psql エラー
  2  設定エラー (production 拒否 / env 不足 / DB 名不一致)
EOF
}

# ---------------------------------------------------------------------------
# 引数パース
# ---------------------------------------------------------------------------
ENV_TARGET=""
for arg in "$@"; do
  case "${arg}" in
    --env=*) ENV_TARGET="${arg#--env=}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] 未知の引数: ${arg}" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${ENV_TARGET}" ]]; then
  echo "[ERROR] --env=staging を指定してください" >&2
  usage >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Guard 1: production 拒否
# ---------------------------------------------------------------------------
if [[ "${ENV_TARGET}" == "production" || "${ENV_TARGET}" == "prod" ]]; then
  echo "[ERROR] production DB への seed は禁止です (--env=${ENV_TARGET} を拒否)" >&2
  echo "        この script は staging 専用です。山本さん本番 user (id=11) を" >&2
  echo "        壊さないため、production への書き込みは一切行いません。" >&2
  exit 2
fi

if [[ "${ENV_TARGET}" != "staging" ]]; then
  echo "[ERROR] サポート外の --env=${ENV_TARGET}。--env=staging のみ受け付けます" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# env 必須チェック
# ---------------------------------------------------------------------------
if [[ -z "${DATABASE_URL:-}" ]]; then
  # .env.staging-new からの fallback ロード (任意)
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  for f in "${PROJECT_ROOT}/.env.staging-new" "${PROJECT_ROOT}/.env.staging"; do
    if [[ -f "${f}" ]]; then
      # shellcheck disable=SC2002
      maybe_url="$(grep -E '^DATABASE_URL=' "${f}" | head -n 1 | cut -d= -f2-)"
      if [[ -n "${maybe_url}" ]]; then
        DATABASE_URL="${maybe_url}"
        echo "[INFO] DATABASE_URL を ${f} から取得しました"
        break
      fi
    fi
  done
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[ERROR] DATABASE_URL が未設定です。staging DB URL を環境変数で指定してください" >&2
  exit 2
fi

if [[ -z "${E2E_PARTNER_PASSWORD_HASH:-}" ]]; then
  echo "[ERROR] E2E_PARTNER_PASSWORD_HASH が未設定です (bcrypt ハッシュ必須)" >&2
  exit 2
fi

if [[ -z "${E2E_PARTNER_WALLET_ADDRESS:-}" ]]; then
  echo "[ERROR] E2E_PARTNER_WALLET_ADDRESS が未設定です (testnet wallet 必須)" >&2
  exit 2
fi

E2E_PARTNER_EMAIL="${E2E_PARTNER_EMAIL:-e2e-partner@ultra-autotrade.local}"

# ---------------------------------------------------------------------------
# psql の存在確認
# ---------------------------------------------------------------------------
if ! command -v psql >/dev/null 2>&1; then
  echo "[ERROR] psql コマンドが見つかりません。postgresql-client をインストールしてください" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Guard 2: DB 名再確認 (DATABASE_URL から DB 名を抽出して staging を含むこと)
# ---------------------------------------------------------------------------
# postgresql://user:pass@host:port/dbname?... の dbname 部分を取り出す
DB_NAME_FROM_URL="$(
  echo "${DATABASE_URL}" \
    | sed -E 's|^postgres(ql)?://[^/]+/||' \
    | sed -E 's|\?.*$||'
)"

# psql 経由で current_database() も取って二重確認
CURRENT_DB="$(psql "${DATABASE_URL}" -tAc 'SELECT current_database()' 2>/dev/null || true)"

if [[ -z "${CURRENT_DB}" ]]; then
  echo "[ERROR] psql で DB に接続できませんでした。DATABASE_URL を確認してください" >&2
  echo "        (URL から抽出した DB 名候補: ${DB_NAME_FROM_URL})" >&2
  exit 1
fi

case "${CURRENT_DB}" in
  *staging*)
    echo "[INFO] DB 名再確認 OK: current_database()=${CURRENT_DB}"
    ;;
  *)
    echo "[ERROR] DB 名に 'staging' が含まれていません: current_database()=${CURRENT_DB}" >&2
    echo "        production DB の可能性があるため seed を中止します (二重ガード)" >&2
    exit 2
    ;;
esac

# ---------------------------------------------------------------------------
# seed 本体
#   ON CONFLICT (id)    → 同一 id で upsert
#   email の unique 制約は別 user に同じ email が居る場合に発火するが、
#   その場合は INSERT が ON CONFLICT (id) ではなく email 衝突で abort する。
#   対策: 事前に email で別 id の row があれば error 出して止める。
#         (=安全側: 想定外の上書きをしない)
# ---------------------------------------------------------------------------
E2E_USER_ID=999998
E2E_USER_USERNAME='e2e-partner'

echo ""
echo "=== seed_e2e_user.sh: target ==="
echo "  DB:              ${CURRENT_DB}"
echo "  user id:         ${E2E_USER_ID}"
echo "  email:           ${E2E_PARTNER_EMAIL}"
echo "  role:            partner"
echo "  execution_policy: require_approval"
echo "  tier:            GENERAL"
echo "  wallet_address:  ${E2E_PARTNER_WALLET_ADDRESS}"
echo ""

# 事前チェック: 同じ email で別 id の row が居ないか
EXISTING_ID_FOR_EMAIL="$(
  psql "${DATABASE_URL}" -tAc \
    "SELECT id FROM users WHERE email = '${E2E_PARTNER_EMAIL}'" 2>/dev/null || true
)"

if [[ -n "${EXISTING_ID_FOR_EMAIL}" && "${EXISTING_ID_FOR_EMAIL}" != "${E2E_USER_ID}" ]]; then
  echo "[ERROR] email '${E2E_PARTNER_EMAIL}' は既に id=${EXISTING_ID_FOR_EMAIL} で使用中です" >&2
  echo "        想定外の上書きを防ぐため seed を中止します。" >&2
  exit 1
fi

# 事前チェック: 同じ wallet_address で別 id の row が居ないか
EXISTING_ID_FOR_WALLET="$(
  psql "${DATABASE_URL}" -tAc \
    "SELECT id FROM users WHERE wallet_address = '${E2E_PARTNER_WALLET_ADDRESS}'" 2>/dev/null || true
)"

if [[ -n "${EXISTING_ID_FOR_WALLET}" && "${EXISTING_ID_FOR_WALLET}" != "${E2E_USER_ID}" ]]; then
  echo "[ERROR] wallet_address は既に id=${EXISTING_ID_FOR_WALLET} で使用中です" >&2
  echo "        E2E_PARTNER_WALLET_ADDRESS を別の testnet address に変えてください。" >&2
  exit 1
fi

# 冪等 upsert
#   ON CONFLICT (id) DO UPDATE で id=999998 を主キーに更新
#   bcrypt ハッシュは $ を含むためシングルクォートで直接渡す
PSQL_SQL=$(cat <<SQL
INSERT INTO users (
    id, email, username, hashed_password, role,
    is_active, execution_policy, tier, wallet_address,
    risk_mode, notification_frequency, user_mode,
    created_at, updated_at
) VALUES (
    ${E2E_USER_ID},
    '${E2E_PARTNER_EMAIL}',
    '${E2E_USER_USERNAME}',
    '${E2E_PARTNER_PASSWORD_HASH}',
    'partner',
    TRUE,
    'require_approval',
    'GENERAL',
    '${E2E_PARTNER_WALLET_ADDRESS}',
    'conservative',
    'important',
    'managed',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    username = EXCLUDED.username,
    hashed_password = EXCLUDED.hashed_password,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active,
    execution_policy = EXCLUDED.execution_policy,
    tier = EXCLUDED.tier,
    wallet_address = EXCLUDED.wallet_address,
    updated_at = NOW();
SQL
)

echo "--- psql INSERT ... ON CONFLICT (id) DO UPDATE ---"
if ! psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -c "${PSQL_SQL}"; then
  echo "[ERROR] psql 実行に失敗しました" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 完了確認
# ---------------------------------------------------------------------------
echo ""
echo "--- seed 後の row 確認 ---"
psql "${DATABASE_URL}" -c \
  "SELECT id, email, role, execution_policy, tier, is_active FROM users WHERE id = ${E2E_USER_ID}"

echo ""
echo "[OK] E2E user seed 完了 (id=${E2E_USER_ID} on ${CURRENT_DB})"
exit 0
