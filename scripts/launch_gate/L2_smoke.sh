#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L2_smoke.sh
#
# Launch Gate L2: 主要 endpoint smoke test。
#
# 目的:
#   /health と主要 5 endpoint が 2xx で応答することを確認する。
#
# 主要 5 endpoint:
#   /api/portfolio
#   /api/transparency/safety-score
#   /api/automation/status
#   /api/ai/decisions/latest
#   /api/proposals/pending
#
# 注意:
#   staging は本番 Hetzner VPS (77.42.46.155) に同居しており dev VPS から
#   到達不可。memory [[staging-lives-on-prod-vps]] / [[no-prod-vps-commands-from-dev]]
#   に従い、dev VPS では skip-with-instructions モードに倒す。
#
# Usage:
#   ENV_TARGET=staging    bash scripts/launch_gate/L2_smoke.sh
#   ENV_TARGET=production bash scripts/launch_gate/L2_smoke.sh
#   LAUNCH_GATE_BASE_URL=http://localhost:8000 bash scripts/launch_gate/L2_smoke.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

LABEL="L2 smoke"
ENV_TARGET="${ENV_TARGET:-staging}"

# 主要 endpoint
ENDPOINTS=(
  "/health"
  "/api/portfolio"
  "/api/transparency/safety-score"
  "/api/automation/status"
  "/api/ai/decisions/latest"
  "/api/proposals/pending"
)

# Base URL (env で override 可能)
case "${ENV_TARGET}" in
  staging)    DEFAULT_BASE="http://localhost:8000" ;;
  production) DEFAULT_BASE="http://localhost:8001" ;;
  *)          DEFAULT_BASE="http://localhost:8000" ;;
esac
BASE_URL="${LAUNCH_GATE_BASE_URL:-${DEFAULT_BASE}}"

# ---------------------------------------------------------------------------
# dev VPS では prod / staging に届かないため skip-with-instructions
# ---------------------------------------------------------------------------
if is_dev_vps; then
  cat <<EOF
[INFO] L2 smoke: dev VPS のため prod VPS 同居の ${ENV_TARGET} に直接到達できません。
       prod VPS (77.42.46.155) で以下のコマンドを実行し、結果を貼り付けてください:

         BASE=${BASE_URL}
$(for ep in "${ENDPOINTS[@]}"; do
    printf '         curl -fsS -o /dev/null -w "%%{http_code} %s\\n" "\$BASE%s"\n' "${ep}" "${ep}"
  done)

       全て 200 番台であること。
       env=${ENV_TARGET} の場合の想定 port:
         staging:    nginx 経由で host:8000 もしくは container 直 (要確認)
         production: nginx 経由で host:8001 もしくは container 直 (要確認)
EOF
  gate_record SKIP "${LABEL}" "dev VPS のため prod VPS で手動 curl 確認 (env=${ENV_TARGET})"
  exit 0
fi

# ---------------------------------------------------------------------------
# 実機 (prod VPS) 実行
# ---------------------------------------------------------------------------
if ! command -v curl >/dev/null 2>&1; then
  gate_record FAIL "${LABEL}" "curl コマンドが無い"
  exit 1
fi

echo "--- L2 smoke: env=${ENV_TARGET} base=${BASE_URL} ---"
fails=()
for ep in "${ENDPOINTS[@]}"; do
  url="${BASE_URL}${ep}"
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${url}" 2>/dev/null || echo "000")
  if [[ "${code}" =~ ^2[0-9][0-9]$ ]]; then
    echo "  [ok] ${code} ${ep}"
  else
    echo "  [ng] ${code} ${ep}"
    fails+=("${ep}=${code}")
  fi
done

if [[ "${#fails[@]}" -eq 0 ]]; then
  gate_record PASS "${LABEL}" "全 ${#ENDPOINTS[@]} endpoint 2xx (env=${ENV_TARGET})"
  exit 0
fi

gate_record FAIL "${LABEL}" "non-2xx: ${fails[*]}"
exit 1
