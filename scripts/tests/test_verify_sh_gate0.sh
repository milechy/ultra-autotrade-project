#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# test_verify_sh_gate0.sh
#
# verify.sh Gate 0 の set -e 安全性テスト
# (NEXT_PUBLIC_DEFAULT_CHAIN_ID 未定義でもスクリプトが継続すること)
#
# 実行:
#   bash scripts/tests/test_verify_sh_gate0.sh
#
# 終了コード:
#   0: 全テスト通過
#   1: 1件以上失敗
# ---------------------------------------------------------------------------
set -uo pipefail

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_TEST}"' EXIT

PASS=0
FAIL=0

_pass() { echo "  ✅ PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "  ❌ FAIL: $1"; FAIL=$(( FAIL + 1 )); }

echo "=== verify.sh Gate 0 set -e 安全性テスト ==="
echo ""

# ---------------------------------------------------------------------------
# Case 1: .env.production に NEXT_PUBLIC_DEFAULT_CHAIN_ID が未定義
#         → Gate 0 skipped (warning) / スクリプトが継続すること
# ---------------------------------------------------------------------------
echo "--- Case 1: CHAIN_ID未定義 → Gate 0 skip (set -e で落ちないこと) ---"
{
  env_file="${TMPDIR_TEST}/c1.env"
  echo "OTHER_KEY=value" > "${env_file}"

  # verify.sh Gate 0 の該当ロジックだけ抽出して set -euo pipefail 下でテスト
  output="$(bash -c "
    set -euo pipefail
    CHAIN_ID=\$(grep '^NEXT_PUBLIC_DEFAULT_CHAIN_ID=' '${env_file}' 2>/dev/null | cut -d= -f2 || true)
    if [ \"\$CHAIN_ID\" = '8453' ]; then
      echo 'GATE0_MAINNET'
    elif [ \"\$CHAIN_ID\" = '84532' ]; then
      echo 'GATE0_SKIP_SEPOLIA'
    else
      echo 'GATE0_SKIP_UNDEFINED'
    fi
    echo 'GATE1_REACHED'
  " 2>&1)"
  exit_code=$?

  if [[ "${exit_code}" -eq 0 ]]; then
    _pass "exit 0 (set -e で落ちない)"
  else
    _fail "exit ${exit_code} — set -e で落ちている (バグ未修正)"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "GATE0_SKIP_UNDEFINED"; then
    _pass "Gate 0 skip (未定義) メッセージ"
  else
    _fail "Gate 0 skip メッセージが出力されない"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "GATE1_REACHED"; then
    _pass "Gate 1 以降に到達"
  else
    _fail "Gate 1 以降に到達できない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 2: .env.production に CHAIN_ID=8453 かつ Sepolia 参照なし
#         → Gate 0 pass
# ---------------------------------------------------------------------------
echo "--- Case 2: CHAIN_ID=8453 + Sepolia参照なし → Gate 0 pass ---"
{
  env_file="${TMPDIR_TEST}/c2.env"
  echo "NEXT_PUBLIC_DEFAULT_CHAIN_ID=8453" > "${env_file}"

  frontend_dir="${TMPDIR_TEST}/frontend_c2"
  mkdir -p "${frontend_dir}/app"
  echo "const chain = 'mainnet'" > "${frontend_dir}/app/config.ts"

  output="$(bash -c "
    set -euo pipefail
    CHAIN_ID=\$(grep '^NEXT_PUBLIC_DEFAULT_CHAIN_ID=' '${env_file}' 2>/dev/null | cut -d= -f2 || true)
    if [ \"\$CHAIN_ID\" = '8453' ]; then
      if grep -rn 'Sepolia' '${frontend_dir}/' 2>/dev/null \
          | grep -v '__mocks__\|\.spec\.\|\.test\.' > /tmp/sepolia_c2.log 2>&1; then
        echo 'GATE0_ERROR'
        exit 1
      fi
      rm -f /tmp/sepolia_c2.log
      echo 'GATE0_PASS'
    fi
    echo 'GATE1_REACHED'
  " 2>&1)"
  exit_code=$?

  if [[ "${exit_code}" -eq 0 ]]; then
    _pass "exit 0"
  else
    _fail "exit ${exit_code} — unexpected failure"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "GATE0_PASS"; then
    _pass "Gate 0 pass"
  else
    _fail "Gate 0 pass メッセージが出力されない"
    echo "    output: ${output}"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 3: .env.production に CHAIN_ID=8453 かつ Sepolia が非テストファイルに存在
#         → Gate 0 エラーで exit 1
# ---------------------------------------------------------------------------
echo "--- Case 3: CHAIN_ID=8453 + Sepolia参照あり (非テスト) → Gate 0 error ---"
{
  env_file="${TMPDIR_TEST}/c3.env"
  echo "NEXT_PUBLIC_DEFAULT_CHAIN_ID=8453" > "${env_file}"

  frontend_dir="${TMPDIR_TEST}/frontend_c3"
  mkdir -p "${frontend_dir}/app"
  echo "const chain = 'Sepolia'" > "${frontend_dir}/app/config.ts"

  output="$(bash -c "
    set -euo pipefail
    CHAIN_ID=\$(grep '^NEXT_PUBLIC_DEFAULT_CHAIN_ID=' '${env_file}' 2>/dev/null | cut -d= -f2 || true)
    if [ \"\$CHAIN_ID\" = '8453' ]; then
      if grep -rn 'Sepolia' '${frontend_dir}/' 2>/dev/null \
          | grep -v '__mocks__\|\.spec\.\|\.test\.' > /tmp/sepolia_c3.log 2>&1; then
        rm -f /tmp/sepolia_c3.log
        echo 'GATE0_ERROR'
        exit 1
      fi
      rm -f /tmp/sepolia_c3.log
      echo 'GATE0_PASS'
    fi
    echo 'GATE1_REACHED'
  " 2>&1)"
  exit_code=$?

  if [[ "${exit_code}" -eq 1 ]]; then
    _pass "exit 1 (実際の Sepolia 参照を検出)"
  else
    _fail "exit ${exit_code} — Sepolia 参照を見逃した"
    echo "    output: ${output}"
  fi

  if echo "${output}" | grep -q "GATE0_ERROR"; then
    _pass "Gate 0 error メッセージ"
  else
    _fail "Gate 0 error メッセージが出力されない"
    echo "    output: ${output}"
  fi

  if ! echo "${output}" | grep -q "GATE1_REACHED"; then
    _pass "Gate 1 には到達しない (正しく中断)"
  else
    _fail "Gate 1 に到達してしまった"
  fi
}
echo ""

# ---------------------------------------------------------------------------
# Case 4: CHAIN_ID=84532 (Sepolia testnet) → Gate 0 skip
# ---------------------------------------------------------------------------
echo "--- Case 4: CHAIN_ID=84532 (Sepolia testnet) → Gate 0 skip ---"
{
  env_file="${TMPDIR_TEST}/c4.env"
  echo "NEXT_PUBLIC_DEFAULT_CHAIN_ID=84532" > "${env_file}"

  output="$(bash -c "
    set -euo pipefail
    CHAIN_ID=\$(grep '^NEXT_PUBLIC_DEFAULT_CHAIN_ID=' '${env_file}' 2>/dev/null | cut -d= -f2 || true)
    if [ \"\$CHAIN_ID\" = '8453' ]; then
      echo 'GATE0_MAINNET'
    elif [ \"\$CHAIN_ID\" = '84532' ]; then
      echo 'GATE0_SKIP_SEPOLIA'
    else
      echo 'GATE0_SKIP_UNDEFINED'
    fi
    echo 'GATE1_REACHED'
  " 2>&1)"
  exit_code=$?

  if [[ "${exit_code}" -eq 0 ]]; then
    _pass "exit 0"
  else
    _fail "exit ${exit_code} — unexpected failure"
  fi

  if echo "${output}" | grep -q "GATE0_SKIP_SEPOLIA"; then
    _pass "Gate 0 skip (Sepolia testnet)"
  else
    _fail "Gate 0 skip メッセージが出力されない"
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
