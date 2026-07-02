#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L1_env.sh
#
# Launch Gate L1: env 分離検査。
#
# 目的:
#   .env.staging と .env.production が意味のある差分を持つこと、
#   .env.production の重要キーが本番値であることを確認する。
#
# 実装:
#   1. 既存 scripts/check_env_separation.sh を呼ぶ (exit 0 必須)
#   2. .env.production の重要キー (APP_ENV=production, AAVE_NETWORK=base 等)
#      を手元 grep でも検証する (二重チェック)
#
# Usage:
#   bash scripts/launch_gate/L1_env.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

PROJECT_ROOT="$(gate_project_root)"
SEP_SCRIPT="${PROJECT_ROOT}/scripts/check_env_separation.sh"
LABEL="L1 env"

PROD_ENV="${PROJECT_ROOT}/.env.production"
STAGING_ENV="${PROJECT_ROOT}/.env.staging"

if [[ ! -f "${SEP_SCRIPT}" ]]; then
  gate_record FAIL "${LABEL}" "check_env_separation.sh が見つかりません: ${SEP_SCRIPT}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: env ファイルが手元にあるか
# ---------------------------------------------------------------------------
missing=()
[[ ! -f "${PROD_ENV}" ]]    && missing+=(".env.production")
[[ ! -f "${STAGING_ENV}" ]] && missing+=(".env.staging")

if [[ "${#missing[@]}" -gt 0 ]]; then
  cat <<EOF
[INFO] L1 env: ${missing[*]} がこの worktree に存在しません。
       2026-07-02移行後、staging と production は別 VPS です。それぞれ以下を実行し、結果を貼り付けてください:

         # production (5.223.88.14):
         ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 \\
           "cd /opt/ultra-autotrade && bash ${SEP_SCRIPT}; grep -E '^(APP_ENV|AAVE_NETWORK|BYBIT_SANDBOX)=' ${PROD_ENV}"

         # staging (188.34.167.142):
         ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142 \\
           "cd /opt/ultra-autotrade && grep -E '^(APP_ENV|AAVE_NETWORK|BYBIT_SANDBOX)=' ${STAGING_ENV}"

       期待値:
         .env.production: APP_ENV=production / AAVE_NETWORK=base / BYBIT_SANDBOX=false
         .env.staging:    APP_ENV=staging    / AAVE_NETWORK=base_sepolia / BYBIT_SANDBOX=true
EOF
  gate_record SKIP "${LABEL}" "${missing[*]} がこの host に無し (production=5.223.88.14 / staging=188.34.167.142 で要手動確認)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 2: check_env_separation.sh
# ---------------------------------------------------------------------------
echo "--- L1 env: check_env_separation.sh ---"
sep_rc=0
bash "${SEP_SCRIPT}" || sep_rc=$?

# ---------------------------------------------------------------------------
# Step 3: 重要キー手元検査 (.env.production の固定値要求)
# ---------------------------------------------------------------------------
echo ""
echo "--- L1 env: .env.production critical keys ---"

violations=()

# APP_ENV=production 必須
app_env=$(grep -E '^APP_ENV=' "${PROD_ENV}" | head -n 1 | cut -d= -f2- | tr -d '[:space:]')
if [[ "${app_env}" != "production" ]]; then
  violations+=("APP_ENV expected=production got='${app_env}'")
  echo "  [ng] APP_ENV='${app_env}' (期待: production)"
else
  echo "  [ok] APP_ENV=production"
fi

# AAVE_NETWORK=base 必須 (Base Mainnet。chains.py CHAIN_REGISTRY のキー名は "base")
aave_net=$(grep -E '^AAVE_NETWORK=' "${PROD_ENV}" | head -n 1 | cut -d= -f2- | tr -d '[:space:]')
if [[ "${aave_net}" != "base" ]]; then
  violations+=("AAVE_NETWORK expected=base got='${aave_net}'")
  echo "  [ng] AAVE_NETWORK='${aave_net}' (期待: base)"
else
  echo "  [ok] AAVE_NETWORK=base"
fi

# DATABASE_URL は存在のみ (値はマスク)
if grep -qE '^DATABASE_URL=' "${PROD_ENV}"; then
  echo "  [ok] DATABASE_URL is set"
else
  violations+=("DATABASE_URL not set in .env.production")
  echo "  [ng] DATABASE_URL 未設定"
fi

# BYBIT_SANDBOX=false 必須 (Phase1 例外期間中は WARN だが、launch gate は厳格)
bybit=$(grep -E '^BYBIT_SANDBOX=' "${PROD_ENV}" | head -n 1 | cut -d= -f2- | tr -d '[:space:]')
if [[ -n "${bybit}" && "${bybit}" != "false" ]]; then
  violations+=("BYBIT_SANDBOX expected=false got='${bybit}'")
  echo "  [ng] BYBIT_SANDBOX='${bybit}' (期待: false)"
else
  echo "  [ok] BYBIT_SANDBOX=${bybit:-(unset)}"
fi

# ---------------------------------------------------------------------------
# 結果集約
# ---------------------------------------------------------------------------
if [[ "${sep_rc}" -ne 0 || "${#violations[@]}" -gt 0 ]]; then
  msg="check_env_separation rc=${sep_rc}"
  if [[ "${#violations[@]}" -gt 0 ]]; then
    msg="${msg}; critical-key NG: ${violations[*]}"
  fi
  gate_record FAIL "${LABEL}" "${msg}"
  exit 1
fi

gate_record PASS "${LABEL}" "env 分離 OK & .env.production の critical key 期待値一致"
exit 0
