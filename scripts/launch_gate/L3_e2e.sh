#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L3_e2e.sh
#
# Launch Gate L3: Playwright e2e (yamamoto-partner-flow.spec.ts) 完走。
#
# 目的:
#   山本さんパートナーフローの e2e がフロント上で完走することを確認する。
#   UI 側の結合崩れ (router 未登録 / 404 / 接続切れ) の最終検出網。
#
# §7 罠防止 (重要):
#   credentials なしで全 test が skip された場合に PASS としない。
#   "NO TESTS RAN — SKIP ONLY" は FAIL 扱い。verify.sh 通過だけでクローズ禁止
#   原則の最後の砦。
#
# 実装:
#   1. credentials 事前確認 (E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD)
#      - 未設定: SKIP-WITH-INSTRUCTIONS (gate_record SKIP, exit 0)
#        → launch_gate サマリでは SKIP として記録 (PASS にしない)
#      - 設定済: playwright を json reporter で実行
#   2. playwright-results.json を jq で解析
#      - failed > 0           → FAIL
#      - passed == 0 (and skipped > 0) → FAIL "NO TESTS RAN"
#      - passed > 0 && failed == 0 → PASS
#
# Usage:
#   ENV_TARGET=staging bash scripts/launch_gate/L3_e2e.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

PROJECT_ROOT="$(gate_project_root)"
LABEL="L3 e2e"
ENV_TARGET="${ENV_TARGET:-staging}"

FRONTEND_DIR="${PROJECT_ROOT}/frontend"
SPEC_REL="e2e/yamamoto-partner-flow.spec.ts"
SPEC_ABS="${FRONTEND_DIR}/${SPEC_REL}"
PW_CONFIG="${FRONTEND_DIR}/playwright.config.ts"
RESULTS_JSON="${FRONTEND_DIR}/playwright-results.json"

# ---------------------------------------------------------------------------
# 前提物存在チェック
# ---------------------------------------------------------------------------
if [[ ! -f "${SPEC_ABS}" ]]; then
  gate_record FAIL "${LABEL}" "spec が見つかりません: ${SPEC_ABS}"
  exit 1
fi
if [[ ! -f "${PW_CONFIG}" ]]; then
  gate_record FAIL "${LABEL}" "playwright.config.ts が見つかりません: ${PW_CONFIG}"
  exit 1
fi

# ---------------------------------------------------------------------------
# credentials 事前確認 (§7 罠防止の入り口)
# ---------------------------------------------------------------------------
HAS_CREDENTIALS=0
if [[ -n "${E2E_PARTNER_EMAIL:-}" && -n "${E2E_PARTNER_PASSWORD:-}" ]]; then
  HAS_CREDENTIALS=1
fi

# ---------------------------------------------------------------------------
# staging 実機を対象にする場合は人間担当 (BASE_URL 切替・認証 token 注入が必要)
# dev VPS で実行する場合も、staging URL に dev から到達できないので skip。
# 実機実行は prod VPS or 開発者ローカルで実施し結果を貼り付けてもらう。
# ---------------------------------------------------------------------------
if is_dev_vps; then
  cat <<EOF
[INFO] L3 e2e: dev VPS のため staging URL ベースの Playwright を直接実行しません。
       下記いずれかの方法で実行し、PASS 出力を貼り付けてください:

         (A) 開発者ローカル (frontend dev サーバを起動した状態):
             cd ${FRONTEND_DIR}
             source /opt/ultra-autotrade/.env.e2e  # staging VPS 上で
             npx playwright test ${SPEC_REL}

         (B) prod VPS (staging 同居) で実行する場合:
             cd /opt/ultra-autotrade/frontend  # prod VPS 側 path
             source /opt/ultra-autotrade/.env.e2e
             PLAYWRIGHT_BASE_URL=https://app-staging.ultra-auto-trade.com \\
               npx playwright test ${SPEC_REL}

       期待: passed > 0 / failed == 0 / "NO TESTS RAN" でないこと。
EOF
  gate_record SKIP "${LABEL}" "dev VPS のため Playwright 実機は手動実行 (yamamoto-partner-flow.spec.ts)"
  exit 0
fi

# ---------------------------------------------------------------------------
# 実機 (prod / 開発者ローカル) で credentials 未設定なら SKIP-WITH-INSTRUCTIONS
# (§7 罠防止: ここで「実行 → 全 skip → 緑」を作らない)
# ---------------------------------------------------------------------------
if [[ "${HAS_CREDENTIALS}" -eq 0 ]]; then
  cat <<EOF
[INFO] L3 e2e: E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD が未設定です。
       skip-only で緑にしないため、テストは実行せず SKIP として記録します。
       実行するには:

         source /opt/ultra-autotrade/.env.e2e
         bash scripts/launch_gate/L3_e2e.sh

       (.env.e2e の中身は frontend/.env.e2e.example を参照)
EOF
  gate_record SKIP "${LABEL}" "credentials 未設定 (NO TESTS RAN を回避するため未実行)"
  exit 0
fi

if ! command -v npx >/dev/null 2>&1; then
  gate_record FAIL "${LABEL}" "npx コマンドが見つからない (Node.js / npm 要インストール)"
  exit 1
fi

# 既存の playwright-results.json は実行前に消す (前回結果が残ると誤判定)
rm -f "${RESULTS_JSON}"

echo "--- L3 e2e: npx playwright test ${SPEC_REL} (json reporter on) ---"
(
  cd "${FRONTEND_DIR}" || exit 1
  npx playwright test "${SPEC_REL}"
)
playwright_rc=$?

# ---------------------------------------------------------------------------
# 結果 JSON 解析 — passed / failed / skipped 件数を集計
#
# playwright json reporter の構造 (simplified):
#   {
#     "stats": { "expected": N, "skipped": N, "unexpected": N, "flaky": N },
#     "suites": [ ... ]
#   }
#
# expected   = passed (期待通り pass) + 期待通り fail
# unexpected = failed (期待外 fail)
# skipped    = skipped
#
# yamamoto-partner-flow.spec.ts には expected="passes" のテストしか無いので
# expected ≒ passed と扱う。flaky は最終的に pass なので passed に加算。
# ---------------------------------------------------------------------------
if [[ ! -f "${RESULTS_JSON}" ]]; then
  gate_record FAIL "${LABEL}" "playwright-results.json が出力されませんでした (rc=${playwright_rc}) — config の json reporter を確認"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  # jq が無い環境 → 後方互換で rc のみ見る (skip-only 判定はできないので警告)
  echo "[WARN] jq が見つからないため json 解析できません。rc のみで判定します。"
  if [[ "${playwright_rc}" -eq 0 ]]; then
    gate_record PASS "${LABEL}" "playwright rc=0 (jq 不在で skip-only 判定 skip)"
    exit 0
  fi
  gate_record FAIL "${LABEL}" "playwright rc=${playwright_rc}"
  exit 1
fi

PASSED=$(jq -r '.stats.expected // 0' "${RESULTS_JSON}" 2>/dev/null || echo 0)
FAILED=$(jq -r '.stats.unexpected // 0' "${RESULTS_JSON}" 2>/dev/null || echo 0)
SKIPPED=$(jq -r '.stats.skipped // 0' "${RESULTS_JSON}" 2>/dev/null || echo 0)
FLAKY=$(jq -r '.stats.flaky // 0' "${RESULTS_JSON}" 2>/dev/null || echo 0)

# 数値防御 (jq が null 返した場合の保険)
PASSED=${PASSED:-0}
FAILED=${FAILED:-0}
SKIPPED=${SKIPPED:-0}
FLAKY=${FLAKY:-0}

# flaky は最終的に pass しているので passed に加算
PASSED_TOTAL=$(( PASSED + FLAKY ))

echo ""
echo "--- L3 e2e: 件数集計 ---"
echo "  passed:  ${PASSED_TOTAL} (expected=${PASSED} + flaky=${FLAKY})"
echo "  failed:  ${FAILED}"
echo "  skipped: ${SKIPPED}"
echo "  playwright rc: ${playwright_rc}"
echo ""

# ---------------------------------------------------------------------------
# 判定 (重要 — §7 罠防止)
# ---------------------------------------------------------------------------
if [[ "${FAILED}" -gt 0 ]]; then
  gate_record FAIL "${LABEL}" \
    "${PASSED_TOTAL} passed / ${SKIPPED} skipped / ${FAILED} failed (詳細: ${RESULTS_JSON})"
  exit 1
fi

if [[ "${PASSED_TOTAL}" -eq 0 ]]; then
  # 全 skip — credentials 設定漏れ or describe レベル skip の可能性
  gate_record FAIL "${LABEL}" \
    "NO TESTS RAN — 0 passed / ${SKIPPED} skipped / 0 failed. credentials 設定漏れの可能性"
  exit 1
fi

# passed > 0 && failed == 0
gate_record PASS "${LABEL}" \
  "${PASSED_TOTAL} passed / ${SKIPPED} skipped / 0 failed (${ENV_TARGET})"
exit 0
