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

# テスト時のファイルパスオーバーライド (scripts/tests/test_check_env_separation.sh が使用)
STAGING_FILE="${STAGING_ENV_FILE:-${PROJECT_ROOT}/.env.staging}"
PRODUCTION_FILE="${PRODUCTION_ENV_FILE:-${PROJECT_ROOT}/.env.production}"

# 両ファイルが揃っていない場合は検証できないのでスキップ（CI で片側のみ存在する場合に配慮）
if [[ ! -f "${STAGING_FILE}" ]] || [[ ! -f "${PRODUCTION_FILE}" ]]; then
  echo "ℹ️  .env.staging または .env.production が存在しません。環境分離チェックをスキップします。"
  echo "    staging:    ${STAGING_FILE}"
  echo "    production: ${PRODUCTION_FILE}"
  exit 0
fi

echo "=== 環境分離チェック: .env.staging vs .env.production ==="

# ---------------------------------------------------------------------------
# Phase 1 例外設定
# Phase 1 期間中は以下の変数が意図的に staging 値のまま .env.production に存在する。
# PHASE1_EXCEPTION_EXPIRES_ON を .env.production から読み取り、期限内なら WARN に格下げ。
# ---------------------------------------------------------------------------
PHASE1_EXCEPTION_VARS=(
  "APP_ENV"
  "BYBIT_SANDBOX"
  "AAVE_NETWORK"
  "AAVE_RPC_URL"
  "EXCHANGE_CLIENT_TYPE"
  "AAVE_POOL_ADDRESS"
)

PHASE1_EXPIRES="$(grep -E '^PHASE1_EXCEPTION_EXPIRES_ON=' "${PRODUCTION_FILE}" | head -n 1 | cut -d= -f2)"
if [[ -z "${PHASE1_EXPIRES}" ]]; then
  echo "❌ ERROR: PHASE1_EXCEPTION_EXPIRES_ON が .env.production に設定されていません。"
  echo "   例: PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"
  echo "   Phase 1 例外ロジックを正しく動作させるために必須です。"
  exit 1
fi

# テスト時の日付オーバーライド (ENV_SEPARATION_TEST_DATE=YYYY-MM-DD で差し替え可能)
TODAY="${ENV_SEPARATION_TEST_DATE:-$(date +%Y-%m-%d)}"
if [[ "${TODAY}" > "${PHASE1_EXPIRES}" ]]; then
  PHASE1_ACTIVE=false
  echo "ℹ️  Phase 1 例外期間が終了しています (PHASE1_EXCEPTION_EXPIRES_ON=${PHASE1_EXPIRES}, TODAY=${TODAY})"
else
  PHASE1_ACTIVE=true
  echo "ℹ️  Phase 1 例外モード有効 (PHASE1_EXCEPTION_EXPIRES_ON=${PHASE1_EXPIRES}, TODAY=${TODAY})"
fi

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

# Phase 1 例外変数か判定
is_phase1_exception_var() {
  local key="$1"
  local v
  for v in "${PHASE1_EXCEPTION_VARS[@]}"; do
    [[ "${v}" == "${key}" ]] && return 0
  done
  return 1
}

# 違反追加: Phase 1 例外中かつ対象変数ならWARNに格下げ、それ以外はVIOLATIONS
_add_violation_or_warn() {
  local key="$1"
  local message="$2"
  if [[ "${PHASE1_ACTIVE}" == "true" ]] && is_phase1_exception_var "${key}"; then
    WARNINGS+=("[Phase1例外 until ${PHASE1_EXPIRES}] ${message}")
  else
    VIOLATIONS+=("${message}")
  fi
}

# ---------------------------------------------------------------------------
# 違反収集
# ---------------------------------------------------------------------------
VIOLATIONS=()
WARNINGS=()

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
    _add_violation_or_warn "${key}" "必須差分キー ${key} が同値: staging=$(display_value "${key}" "${staging_val}") / production=$(display_value "${key}" "${production_val}")"
    if [[ "${PHASE1_ACTIVE}" == "true" ]] && is_phase1_exception_var "${key}"; then
      echo "  ⚠️  ${key}: staging==production (Phase1例外: WARN)"
    else
      echo "  ❌ ${key}: staging=$(display_value "${key}" "${staging_val}") == production=$(display_value "${key}" "${production_val}")"
    fi
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
  _add_violation_or_warn "APP_ENV" ".env.production に APP_ENV=staging が含まれています"
  if [[ "${PHASE1_ACTIVE}" == "true" ]] && is_phase1_exception_var "APP_ENV"; then
    echo "  ⚠️  APP_ENV=staging を検出 (Phase1例外: WARN)"
  else
    echo "  ❌ APP_ENV=staging を検出"
  fi
else
  echo "  ✅ APP_ENV=staging なし"
fi

if grep -qE '^BYBIT_SANDBOX=true[[:space:]]*$' "${PRODUCTION_FILE}"; then
  _add_violation_or_warn "BYBIT_SANDBOX" ".env.production に BYBIT_SANDBOX=true が含まれています (本番は false 必須)"
  if [[ "${PHASE1_ACTIVE}" == "true" ]] && is_phase1_exception_var "BYBIT_SANDBOX"; then
    echo "  ⚠️  BYBIT_SANDBOX=true を検出 (Phase1例外: WARN)"
  else
    echo "  ❌ BYBIT_SANDBOX=true を検出"
  fi
else
  echo "  ✅ BYBIT_SANDBOX=true なし"
fi

if grep -qiE '^AAVE_NETWORK=.*sepolia.*' "${PRODUCTION_FILE}"; then
  _add_violation_or_warn "AAVE_NETWORK" ".env.production に AAVE_NETWORK の sepolia 指定が含まれています (本番は mainnet 必須)"
  if [[ "${PHASE1_ACTIVE}" == "true" ]] && is_phase1_exception_var "AAVE_NETWORK"; then
    echo "  ⚠️  AAVE_NETWORK=*sepolia* を検出 (Phase1例外: WARN)"
  else
    echo "  ❌ AAVE_NETWORK=*sepolia* を検出"
  fi
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
# AI モデル名検証
# ---------------------------------------------------------------------------
echo ""
echo "--- AI モデル名チェック ---"

_DEPRECATED_AI_MODELS=(
  "claude-sonnet-4-20250514"
  "claude-3-5-sonnet-20241022"
  "claude-3-5-sonnet-latest"
  "claude-3-opus-20240229"
)

_validate_ai_model_names() {
  local env_file="$1"
  local env_label="$2"
  local ok=0

  for pattern in "${_DEPRECATED_AI_MODELS[@]}"; do
    if grep -qE "^(AI_CLAUDE_MODEL|AI_FALLBACK_MODEL)=.*${pattern}" "${env_file}"; then
      VIOLATIONS+=("非推奨 Claude モデルが ${env_label} に設定されています: ${pattern}")
      echo "  ❌ 非推奨モデル検出 [${env_label}]: ${pattern}"
      ok=1
    fi
  done

  local claude_model
  claude_model="$(get_value "${env_file}" "AI_CLAUDE_MODEL")"
  if [[ -z "${claude_model}" ]]; then
    VIOLATIONS+=("AI_CLAUDE_MODEL が ${env_label} に未設定です")
    echo "  ❌ AI_CLAUDE_MODEL 未設定 [${env_label}]"
    ok=1
  else
    echo "  ✅ AI_CLAUDE_MODEL [${env_label}]: ${claude_model}"
  fi

  return "${ok}"
}

_validate_ai_model_names "${PRODUCTION_FILE}" "production"
_validate_ai_model_names "${STAGING_FILE}" "staging"

# ---------------------------------------------------------------------------
# 結果サマリ
# ---------------------------------------------------------------------------
echo ""
echo "=== 結果 ==="

if [[ "${#WARNINGS[@]}" -gt 0 ]]; then
  echo "⚠️  Phase 1 例外 WARN: ${#WARNINGS[@]} 件 (exit 0)"
  for w in "${WARNINGS[@]}"; do
    echo "   - ${w}"
  done
fi

if [[ "${#VIOLATIONS[@]}" -eq 0 ]]; then
  echo "✅ 環境分離チェック: 全項目通過"
  exit 0
fi

echo "❌ 環境分離チェック: ${#VIOLATIONS[@]} 件の違反を検出"
for v in "${VIOLATIONS[@]}"; do
  echo "   - ${v}"
done
exit 1
