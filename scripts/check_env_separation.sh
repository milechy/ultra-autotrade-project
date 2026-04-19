#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# check_env_separation.sh
#
# .env.staging と .env.production が意味のある差分を持っているか検証する。
#
# 背景:
#   2026-04-18 の sed 一斉更新インシデントで両ファイルが完全一致状態に陥り、
#   本番コンテナに APP_ENV=staging / BYBIT_SANDBOX=true / AAVE_NETWORK=base_sepolia
#   が残存していた。再発防止のために CI / deploy スクリプトから呼び出す。
#
# 終了コード:
#   0: 全チェック通過（ファイルが存在しない場合もスキップして 0）
#   1: 検証失敗（違反キーを標準出力に列挙）
#
# 実行:
#   bash scripts/check_env_separation.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STAGING_FILE="${PROJECT_ROOT}/.env.staging"
PRODUCTION_FILE="${PROJECT_ROOT}/.env.production"

# 両ファイルが揃っていない場合は検証できないのでスキップ（CI で片側のみ存在する場合に配慮）
if [[ ! -f "${STAGING_FILE}" ]] || [[ ! -f "${PRODUCTION_FILE}" ]]; then
  echo "ℹ️  .env.staging または .env.production が存在しません。環境分離チェックをスキップします。"
  echo "    staging:    ${STAGING_FILE}"
  echo "    production: ${PRODUCTION_FILE}"
  exit 0
fi

echo "=== 環境分離チェック: .env.staging vs .env.production ==="

# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

# 値取得: 最初にマッチする `KEY=VALUE` の VALUE 部分を返す（コメント行を除外）
get_value() {
  local file="$1"
  local key="$2"
  grep -E "^${key}=" "${file}" 2>/dev/null | head -n 1 | sed -E "s/^${key}=//"
}

# 秘密情報っぽいキーか判定
is_secret_key() {
  local key="$1"
  case "${key}" in
    *API_KEY*|*SECRET*|*PASSWORD*|*PRIVATE_KEY*|*TOKEN*|*DATABASE_URL*|*DB_URL*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# 値をマスク表示（秘密情報の場合は *** に置換）
# DATABASE_URL 等の URL に埋め込まれたパスワードも誤表示しないよう注意
display_value() {
  local key="$1"
  local value="$2"
  if is_secret_key "${key}"; then
    echo "***"
  else
    echo "${value}"
  fi
}

# ---------------------------------------------------------------------------
# 違反収集
# ---------------------------------------------------------------------------
VIOLATIONS=()

# ---------------------------------------------------------------------------
# 必須差分キー: 以下のいずれか1個でも同値なら違反
# ---------------------------------------------------------------------------
REQUIRED_DIFF_KEYS=(
  "APP_ENV"
  "AAVE_NETWORK"
  "BYBIT_SANDBOX"
  "POSTGRES_DB"
  "DATABASE_URL"
  "CORS_ORIGINS"
  "NEXT_PUBLIC_API_URL"
)

echo ""
echo "--- 必須差分キーチェック ---"
for key in "${REQUIRED_DIFF_KEYS[@]}"; do
  staging_val="$(get_value "${STAGING_FILE}" "${key}")"
  production_val="$(get_value "${PRODUCTION_FILE}" "${key}")"

  # どちらも未定義なら、そのキー自体を使っていないものとしてスキップ
  if [[ -z "${staging_val}" ]] && [[ -z "${production_val}" ]]; then
    echo "  - ${key}: 両方未定義 (スキップ)"
    continue
  fi

  if [[ "${staging_val}" == "${production_val}" ]]; then
    VIOLATIONS+=("必須差分キー ${key} が同値: staging=$(display_value "${key}" "${staging_val}") / production=$(display_value "${key}" "${production_val}")")
    echo "  ❌ ${key}: staging=$(display_value "${key}" "${staging_val}") == production=$(display_value "${key}" "${production_val}")"
  else
    echo "  ✅ ${key}: 差分あり"
  fi
done

# ---------------------------------------------------------------------------
# 全キー差分ゼロチェック (sed 一斉更新の疑い)
# ---------------------------------------------------------------------------
echo ""
echo "--- 全キー差分チェック (sed 一斉更新の疑い検出) ---"

# 両ファイルのキーの和集合
ALL_KEYS="$(
  {
    grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${STAGING_FILE}" | cut -d= -f1
    grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${PRODUCTION_FILE}" | cut -d= -f1
  } | sort -u
)"

DIFF_COUNT=0
SHARED_COUNT=0
for key in ${ALL_KEYS}; do
  staging_val="$(get_value "${STAGING_FILE}" "${key}")"
  production_val="$(get_value "${PRODUCTION_FILE}" "${key}")"
  if [[ "${staging_val}" != "${production_val}" ]]; then
    DIFF_COUNT=$(( DIFF_COUNT + 1 ))
  else
    SHARED_COUNT=$(( SHARED_COUNT + 1 ))
  fi
done

echo "  差分キー: ${DIFF_COUNT} / 共通キー: ${SHARED_COUNT}"
if [[ "${DIFF_COUNT}" -eq 0 ]]; then
  VIOLATIONS+=("全キーで差分がゼロ: sed 一斉更新によって両ファイルが完全一致した疑いがあります")
  echo "  ❌ 差分ゼロ: sed 一斉更新の疑い"
else
  echo "  ✅ 差分あり"
fi

# ---------------------------------------------------------------------------
# 禁止パターン: .env.production
# ---------------------------------------------------------------------------
echo ""
echo "--- 禁止パターンチェック (.env.production) ---"

if grep -qE '^APP_ENV=staging[[:space:]]*$' "${PRODUCTION_FILE}"; then
  VIOLATIONS+=(".env.production に APP_ENV=staging が含まれています")
  echo "  ❌ APP_ENV=staging を検出"
else
  echo "  ✅ APP_ENV=staging なし"
fi

if grep -qE '^BYBIT_SANDBOX=true[[:space:]]*$' "${PRODUCTION_FILE}"; then
  VIOLATIONS+=(".env.production に BYBIT_SANDBOX=true が含まれています (本番は false 必須)")
  echo "  ❌ BYBIT_SANDBOX=true を検出"
else
  echo "  ✅ BYBIT_SANDBOX=true なし"
fi

if grep -qiE '^AAVE_NETWORK=.*sepolia.*' "${PRODUCTION_FILE}"; then
  VIOLATIONS+=(".env.production に AAVE_NETWORK の sepolia 指定が含まれています (本番は mainnet 必須)")
  echo "  ❌ AAVE_NETWORK=*sepolia* を検出"
else
  echo "  ✅ AAVE_NETWORK に sepolia 含まず"
fi

# ---------------------------------------------------------------------------
# 禁止パターン: .env.staging
# ---------------------------------------------------------------------------
echo ""
echo "--- 禁止パターンチェック (.env.staging) ---"

if grep -qE '^APP_ENV=production[[:space:]]*$' "${STAGING_FILE}"; then
  VIOLATIONS+=(".env.staging に APP_ENV=production が含まれています")
  echo "  ❌ APP_ENV=production を検出"
else
  echo "  ✅ APP_ENV=production なし"
fi

# ---------------------------------------------------------------------------
# 結果サマリ
# ---------------------------------------------------------------------------
echo ""
echo "=== 結果 ==="
if [[ "${#VIOLATIONS[@]}" -eq 0 ]]; then
  echo "✅ 環境分離チェック: 全項目通過"
  exit 0
fi

echo "❌ 環境分離チェック: ${#VIOLATIONS[@]} 件の違反を検出"
for v in "${VIOLATIONS[@]}"; do
  echo "   - ${v}"
done
exit 1
