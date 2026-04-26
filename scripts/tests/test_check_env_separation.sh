#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# test_check_env_separation.sh
#
# check_env_separation.sh の Phase 1 例外ロジックのテスト
#
# 実行:
#   bash scripts/tests/test_check_env_separation.sh
#
# 終了コード:
#   0: 全テスト通過
#   1: 1件以上失敗
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="${SCRIPT_DIR}/../check_env_separation.sh"
TMPDIR_TEST="$(mktemp -d)"

PASS=0
FAIL=0

trap 'rm -rf "${TMPDIR_TEST}"' EXIT

_pass() { echo "  ✅ PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "  ❌ FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# mock env ファイルを生成するヘルパー
# 引数: ファイルパス, キー=値 のペア (残りすべて)
make_env() {
  local file="$1"; shift
  : > "${file}"
  for kv in "$@"; do
    echo "${kv}" >> "${file}"
  done
}

# スクリプトを実行して exit code と stdout を取得
run_check() {
  local staging="$1"
  local production="$2"
  local test_date="${3:-2026-04-26}"
  STAGING_ENV_FILE="${staging}" \
  PRODUCTION_ENV_FILE="${production}" \
  ENV_SEPARATION_TEST_DATE="${test_date}" \
  bash "${CHECK_SCRIPT}" 2>&1
}

# ---------------------------------------------------------------------------
# 共通変数 (テスト全体で使用)
# ---------------------------------------------------------------------------
COMMON_AI_MODEL="AI_CLAUDE_MODEL=claude-sonnet-4-6"
COMMON_STAGING_ONLY=(
  "POSTGRES_DB=ultra_staging"
  "DATABASE_URL=postgresql://ultra:pw@postgres:5432/ultra_staging"
  "CORS_ORIGINS=https://staging.example.com"
  "NEXT_PUBLIC_API_URL=https://staging.example.com"
)
COMMON_PROD_ONLY=(
  "POSTGRES_DB=ultra_production"
  "DATABASE_URL=postgresql://ultra:pw@postgres:5432/ultra_production"
  "CORS_ORIGINS=https://app.example.com"
  "NEXT_PUBLIC_API_URL=https://app.example.com"
)
PHASE1_VARS_STAGING=(
  "APP_ENV=staging"
  "BYBIT_SANDBOX=true"
  "AAVE_NETWORK=base_sepolia"
)
# ---------------------------------------------------------------------------

echo "=== check_env_separation.sh テスト ==="
echo ""

# ---------------------------------------------------------------------------
# Case 1: Phase 1 期間内 + 例外変数差分 → exit 0 + WARN
# ---------------------------------------------------------------------------
echo "--- Case 1: Phase1期間内 + 例外変数差分 → exit 0 + WARN ---"
{
  staging="${TMPDIR_TEST}/c1_staging.env"
  production="${TMPDIR_TEST}/c1_prod.env"

  make_env "${staging}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_STAGING_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  make_env "${production}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_PROD_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  output="$(run_check "${staging}" "${production}" "2026-04-26")"
  exit_code=$?

  if [[ "${exit_code}" -eq 0 ]]; then
    _pass "exit 0"
  else
    _fail "exit 0 が期待値、実際: ${exit_code}"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "Phase1例外"; then
    _pass "WARN メッセージ出力"
  else
    _fail "WARN メッセージが出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 2: Phase 1 期間外 + 例外変数差分 → exit 1
# ---------------------------------------------------------------------------
echo "--- Case 2: Phase1期間外 + 例外変数差分 → exit 1 ---"
{
  staging="${TMPDIR_TEST}/c2_staging.env"
  production="${TMPDIR_TEST}/c2_prod.env"

  make_env "${staging}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_STAGING_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2025-12-31"

  make_env "${production}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_PROD_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2025-12-31"

  output="$(run_check "${staging}" "${production}" "2026-04-26")"
  exit_code=$?

  if [[ "${exit_code}" -eq 1 ]]; then
    _pass "exit 1"
  else
    _fail "exit 1 が期待値、実際: ${exit_code}"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "Phase 1 例外期間が終了"; then
    _pass "期間終了メッセージ出力"
  else
    _fail "期間終了メッセージが出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 3: 例外外変数 (DATABASE_URL) が同値 → 常に exit 1
# ---------------------------------------------------------------------------
echo "--- Case 3: 例外外変数が同値 → 常に exit 1 ---"
{
  staging="${TMPDIR_TEST}/c3_staging.env"
  production="${TMPDIR_TEST}/c3_prod.env"

  # POSTGRES_DB / DATABASE_URL が同値 = 必須差分キー違反 (Phase1例外対象外)
  make_env "${staging}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "POSTGRES_DB=ultra_same" \
    "DATABASE_URL=postgresql://ultra:pw@postgres:5432/ultra_same" \
    "CORS_ORIGINS=https://staging.example.com" \
    "NEXT_PUBLIC_API_URL=https://staging.example.com" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  make_env "${production}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "POSTGRES_DB=ultra_same" \
    "DATABASE_URL=postgresql://ultra:pw@postgres:5432/ultra_same" \
    "CORS_ORIGINS=https://app.example.com" \
    "NEXT_PUBLIC_API_URL=https://app.example.com" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  output="$(run_check "${staging}" "${production}" "2026-04-26")"
  exit_code=$?

  if [[ "${exit_code}" -eq 1 ]]; then
    _pass "Phase1期間内でも例外外変数違反 → exit 1"
  else
    _fail "exit 1 が期待値、実際: ${exit_code}"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -qE "POSTGRES_DB|DATABASE_URL"; then
    _pass "違反キー (DATABASE_URL/POSTGRES_DB) がエラーに出力"
  else
    _fail "違反キーがエラー出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 4: PHASE1_EXCEPTION_EXPIRES_ON 未設定 → exit 1
# ---------------------------------------------------------------------------
echo "--- Case 4: PHASE1_EXCEPTION_EXPIRES_ON未設定 → exit 1 ---"
{
  staging="${TMPDIR_TEST}/c4_staging.env"
  production="${TMPDIR_TEST}/c4_prod.env"

  make_env "${staging}" \
    "APP_ENV=staging" \
    "${COMMON_STAGING_ONLY[@]}" \
    "${COMMON_AI_MODEL}"

  make_env "${production}" \
    "APP_ENV=production" \
    "${COMMON_PROD_ONLY[@]}" \
    "${COMMON_AI_MODEL}"
  # PHASE1_EXCEPTION_EXPIRES_ON は意図的に設定しない

  output="$(run_check "${staging}" "${production}" "2026-04-26")"
  exit_code=$?

  if [[ "${exit_code}" -eq 1 ]]; then
    _pass "exit 1"
  else
    _fail "exit 1 が期待値、実際: ${exit_code}"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "PHASE1_EXCEPTION_EXPIRES_ON"; then
    _pass "設定要求メッセージ出力"
  else
    _fail "設定要求メッセージが出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 5: 全項目通過 (Phase1例外WARNのみ) → exit 0
# ---------------------------------------------------------------------------
echo "--- Case 5: 全項目通過 (Phase1例外WARNのみ) → exit 0 ---"
{
  staging="${TMPDIR_TEST}/c5_staging.env"
  production="${TMPDIR_TEST}/c5_prod.env"

  make_env "${staging}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_STAGING_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  make_env "${production}" \
    "${PHASE1_VARS_STAGING[@]}" \
    "${COMMON_PROD_ONLY[@]}" \
    "${COMMON_AI_MODEL}" \
    "PHASE1_EXCEPTION_EXPIRES_ON=2026-09-30"

  output="$(run_check "${staging}" "${production}" "2026-06-01")"
  exit_code=$?

  if [[ "${exit_code}" -eq 0 ]]; then
    _pass "exit 0"
  else
    _fail "exit 0 が期待値、実際: ${exit_code}"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "全項目通過"; then
    _pass "全項目通過メッセージ出力"
  else
    _fail "全項目通過メッセージが出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# 結果
# ---------------------------------------------------------------------------
echo "=== テスト結果 ==="
echo "  通過: ${PASS} / 失敗: ${FAIL}"
if [[ "${FAIL}" -eq 0 ]]; then
  echo "✅ 全テスト通過"
  exit 0
else
  echo "❌ ${FAIL} 件のテスト失敗"
  exit 1
fi
