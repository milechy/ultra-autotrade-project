#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# tests/launch_gate/test_assert_not_skip_only.sh
#
# scripts/launch_gate/lib.sh の skip-only 構造的判定 helper を smoke test。
#
# 対象 helper:
#   - assert_not_skip_only_playwright (Playwright JSON 入力)
#   - assert_not_skip_only_pytest     (pytest log 入力)
#
# Fixture: tests/launch_gate/fixtures/
#   - playwright_skip_only.json   → exit 1 (skip-only)
#   - playwright_all_passed.json  → exit 0
#   - playwright_mixed.json       → exit 0 (failed > 0 は別 check に委ねる)
#   - pytest_skip_only.log        → exit 1
#   - pytest_all_passed.log       → exit 0
#   - pytest_mixed.log            → exit 0
#
# Usage:
#   bash tests/launch_gate/test_assert_not_skip_only.sh
#   echo $?   # 0 = 全 case 期待通り, 1 以上 = 失敗件数
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FIXTURES="${SCRIPT_DIR}/fixtures"

# shellcheck disable=SC1091
source "${ROOT}/scripts/launch_gate/lib.sh"

pass=0
fail=0
total=0

run_case() {
  local name="$1" expected_rc="$2"
  shift 2
  total=$((total + 1))
  local actual_rc
  if "$@" >/dev/null 2>&1; then
    actual_rc=0
  else
    actual_rc=$?
  fi
  if [[ "${actual_rc}" -eq "${expected_rc}" ]]; then
    echo "  [PASS] ${name}  (rc=${actual_rc})"
    pass=$((pass + 1))
  else
    echo "  [FAIL] ${name}  (expected rc=${expected_rc}, actual rc=${actual_rc})"
    fail=$((fail + 1))
  fi
}

echo "=== smoke: assert_not_skip_only_playwright ==="
run_case "skip_only.json   → FAIL (rc=1)" 1 \
  assert_not_skip_only_playwright "${FIXTURES}/playwright_skip_only.json"
run_case "all_passed.json  → PASS (rc=0)" 0 \
  assert_not_skip_only_playwright "${FIXTURES}/playwright_all_passed.json"
run_case "mixed.json       → PASS (rc=0)" 0 \
  assert_not_skip_only_playwright "${FIXTURES}/playwright_mixed.json"

echo ""
echo "=== smoke: assert_not_skip_only_pytest ==="
run_case "skip_only.log    → FAIL (rc=1)" 1 \
  assert_not_skip_only_pytest "${FIXTURES}/pytest_skip_only.log"
run_case "all_passed.log   → PASS (rc=0)" 0 \
  assert_not_skip_only_pytest "${FIXTURES}/pytest_all_passed.log"
run_case "mixed.log        → PASS (rc=0)" 0 \
  assert_not_skip_only_pytest "${FIXTURES}/pytest_mixed.log"

echo ""
echo "--- Result: ${pass}/${total} passed, ${fail} failed ---"
exit "${fail}"
