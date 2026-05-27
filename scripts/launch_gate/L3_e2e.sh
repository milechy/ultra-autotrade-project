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
# 実装:
#   frontend/e2e/yamamoto-partner-flow.spec.ts を対象に
#   `npx playwright test e2e/yamamoto-partner-flow.spec.ts` を実行する。
#   実機 staging URL に対する e2e は人間担当 (BASE_URL 切替が必要なため)、
#   dev VPS 上で実行可能 (= 依存揃っている) ならローカル実行を試みる。
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
             npx playwright test ${SPEC_REL}

         (B) prod VPS (staging 同居) で実行する場合:
             cd /opt/ultra-autotrade/frontend  # prod VPS 側 path
             PLAYWRIGHT_BASE_URL=https://staging.<...> npx playwright test ${SPEC_REL}

       期待: 1 passed (X.XXs) で exit 0 であること。
EOF
  gate_record SKIP "${LABEL}" "dev VPS のため Playwright 実機は手動実行 (yamamoto-partner-flow.spec.ts)"
  exit 0
fi

# ---------------------------------------------------------------------------
# 実機 (prod / 開発者ローカル) で実行可能なら実行
# ---------------------------------------------------------------------------
if ! command -v npx >/dev/null 2>&1; then
  gate_record FAIL "${LABEL}" "npx コマンドが見つからない (Node.js / npm 要インストール)"
  exit 1
fi

echo "--- L3 e2e: npx playwright test ${SPEC_REL} ---"
(
  cd "${FRONTEND_DIR}" || exit 1
  npx playwright test "${SPEC_REL}"
)
rc=$?

if [[ "${rc}" -eq 0 ]]; then
  gate_record PASS "${LABEL}" "yamamoto-partner-flow.spec.ts 完走"
  exit 0
fi

gate_record FAIL "${LABEL}" "playwright test rc=${rc}"
exit 1
