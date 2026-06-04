#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L4_killswitch.sh
#
# Launch Gate L4: 緊急停止 (kill switch) 動作確認。
#
# 目的:
#   POST /api/automation/emergency-stop が staging で動作し、
#   その後 /api/automation/status が is_trading_paused=true を返すことを確認する。
#
# 注意:
#   staging に dev VPS からは到達不可。skip-with-instructions を出して
#   人間に手元で実行してもらう (memory [[no-prod-vps-commands-from-dev]])。
#
# Usage:
#   ENV_TARGET=staging bash scripts/launch_gate/L4_killswitch.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

LABEL="L4 kill switch"
ENV_TARGET="${ENV_TARGET:-staging}"

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
[INFO] L4 kill switch: dev VPS のため prod VPS 同居の ${ENV_TARGET} に到達できません。
       prod VPS (77.42.46.155) で以下を実行し、結果を貼り付けてください:

         BASE=${BASE_URL}
         # 1) 緊急停止
         curl -fsS -X POST "\$BASE/api/automation/emergency-stop" \\
           -H 'Content-Type: application/json' \\
           -d '{"reason":"launch-gate L4 verification"}'

         # 2) 直後の status で is_trading_paused=true を確認
         curl -fsS "\$BASE/api/automation/status" | jq '.is_trading_paused'

       期待: 1) 2xx 応答, 2) "true" が返る。
       検証後は自動取引を意図的に再開する必要がある場合のみ resume API を叩く。
EOF
  gate_record SKIP "${LABEL}" "dev VPS のため手動 curl 確認 (POST /api/automation/emergency-stop → status.is_trading_paused=true)"
  exit 0
fi

# ---------------------------------------------------------------------------
# 実機 (prod VPS) 実行
# ---------------------------------------------------------------------------
if ! command -v curl >/dev/null 2>&1; then
  gate_record FAIL "${LABEL}" "curl コマンドが無い"
  exit 1
fi

echo "--- L4 kill switch: env=${ENV_TARGET} base=${BASE_URL} ---"

# 1) emergency-stop
stop_code=$(curl -sS -o /tmp/launch_gate_l4_stop.json -w '%{http_code}' \
  --max-time 10 \
  -X POST "${BASE_URL}/api/automation/emergency-stop" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"launch-gate L4 verification"}' 2>/dev/null || echo "000")
echo "  emergency-stop: ${stop_code}"

if [[ ! "${stop_code}" =~ ^2[0-9][0-9]$ ]]; then
  gate_record FAIL "${LABEL}" "emergency-stop response=${stop_code}"
  exit 1
fi

# 2) status 確認
status_body=$(curl -sS --max-time 10 "${BASE_URL}/api/automation/status" 2>/dev/null || echo "")
echo "  status body: ${status_body}"

paused=""
if command -v jq >/dev/null 2>&1; then
  paused=$(echo "${status_body}" | jq -r '.is_trading_paused // empty' 2>/dev/null || echo "")
else
  # jq 無くても可: 雑 grep フォールバック
  if echo "${status_body}" | grep -qE '"is_trading_paused"[[:space:]]*:[[:space:]]*true'; then
    paused="true"
  elif echo "${status_body}" | grep -qE '"is_trading_paused"[[:space:]]*:[[:space:]]*false'; then
    paused="false"
  fi
fi

if [[ "${paused}" == "true" ]]; then
  gate_record PASS "${LABEL}" "emergency-stop → is_trading_paused=true"
  exit 0
fi

gate_record FAIL "${LABEL}" "emergency-stop 後 is_trading_paused='${paused}' (期待: true)"
exit 1
