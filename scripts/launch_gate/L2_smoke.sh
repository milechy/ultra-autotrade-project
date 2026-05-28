#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L2_smoke.sh
#
# Launch Gate L2: 主要 endpoint smoke test。
#
# 目的:
#   /health と主要 5 API endpoint がアプリ層まで届いていることを確認する。
#   認証必須 EP は SMOKE_AUTH_TOKEN が設定されていれば Bearer 付きで 2xx を、
#   未設定なら 401/403 を「到達 OK」(reachable) として PASS 扱いする。
#
# 主要 endpoint:
#   /health                              (public)
#   /api/portfolio                       (auth required)
#   /api/transparency/safety-score       (auth required)
#   /api/automation/status               (auth required)
#   /api/ai/decisions/latest             (auth required)
#   /api/proposals/pending               (auth required)
#
# 判定ロジック (Asana 1215155399947078 / 修正方針 B + A フォールバック):
#   /health:
#     2xx                                    -> PASS
#     その他                                 -> FAIL
#   /api/* (auth required):
#     2xx                                    -> PASS
#     401 / 403                              -> PASS (reachable: app 層まで届いている)
#                                              ※SMOKE_AUTH_TOKEN 設定済の場合は
#                                                token 切れ等の可能性があるため WARN を併記
#     5xx / 接続拒否 / timeout (000)         -> FAIL (app down 疑い)
#     その他 4xx (404 / 400 / 503 等以外)    -> FAIL (endpoint 消失 / 経路破損)
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
#   SMOKE_AUTH_TOKEN=eyJ... bash scripts/launch_gate/L2_smoke.sh   # 2xx まで検証
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

LABEL="L2 smoke"
ENV_TARGET="${ENV_TARGET:-staging}"
SMOKE_AUTH_TOKEN="${SMOKE_AUTH_TOKEN:-}"

# 主要 endpoint と auth-required フラグ ("path|auth" 形式)
ENDPOINTS=(
  "/health|public"
  "/api/portfolio|auth"
  "/api/transparency/safety-score|auth"
  "/api/automation/status|auth"
  "/api/ai/decisions/latest|auth"
  "/api/proposals/pending|auth"
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
         # /health は 2xx 必須
         curl -sS -o /dev/null -w "%{http_code} /health\\n" "\$BASE/health"
         # /api/* は SMOKE_AUTH_TOKEN 設定済なら 2xx、未設定なら 401/403 でも到達 OK
$(for entry in "${ENDPOINTS[@]}"; do
    ep="${entry%%|*}"
    [[ "${ep}" == "/health" ]] && continue
    printf '         curl -sS -o /dev/null -w "%%{http_code} %s\\n" "$BASE%s"\n' "${ep}" "${ep}"
    printf '         # token 付きで 2xx を確認したい場合:\n'
    printf '         # curl -sS -o /dev/null -w "%%{http_code} %s\\n" -H "Authorization: Bearer $SMOKE_AUTH_TOKEN" "$BASE%s"\n' "${ep}" "${ep}"
  done)

       判定:
         /health        : 2xx 必須
         /api/*         : 2xx / 401 / 403 のいずれかなら到達 OK
                          5xx / connection refused / timeout は FAIL

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

if [[ -n "${SMOKE_AUTH_TOKEN}" ]]; then
  echo "--- L2 smoke: env=${ENV_TARGET} base=${BASE_URL} (auth: Bearer token, 2xx 検証) ---"
else
  echo "--- L2 smoke: env=${ENV_TARGET} base=${BASE_URL} (auth: none, 401/403 を到達 OK 扱い) ---"
fi

fails=()
warns=()
for entry in "${ENDPOINTS[@]}"; do
  ep="${entry%%|*}"
  kind="${entry##*|}"
  url="${BASE_URL}${ep}"

  # auth-required EP かつ token あり → Bearer 付与
  curl_auth_args=()
  if [[ "${kind}" == "auth" ]] && [[ -n "${SMOKE_AUTH_TOKEN}" ]]; then
    curl_auth_args=(-H "Authorization: Bearer ${SMOKE_AUTH_TOKEN}")
  fi

  # curl は -w '%{http_code}' で connection refused / timeout 時も "000" を出す。
  # 旧コードは `|| echo "000"` で重複出力していたため除去。
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${curl_auth_args[@]}" "${url}" 2>/dev/null)
  code="${code:-000}"

  if [[ "${code}" =~ ^2[0-9][0-9]$ ]]; then
    echo "  [ok]        ${code} ${ep}"
    continue
  fi

  # /health は 2xx 必須 (public なので 401/403 は異常)
  if [[ "${kind}" == "public" ]]; then
    echo "  [ng]        ${code} ${ep} (public EP は 2xx 必須)"
    fails+=("${ep}=${code}")
    continue
  fi

  # auth EP: 401/403 は到達 OK (アプリ層まで届いた証拠)
  if [[ "${code}" == "401" ]] || [[ "${code}" == "403" ]]; then
    if [[ -n "${SMOKE_AUTH_TOKEN}" ]]; then
      # token 付きで 401/403 が返ったら token 切れ等の可能性 — PASS だが WARN
      echo "  [reachable] ${code} ${ep} (auth token 設定済だが ${code}: token 切れ / scope 不足の可能性)"
      warns+=("${ep}=${code}")
    else
      echo "  [reachable] ${code} ${ep} (auth-required, token 未設定 → 到達 OK 扱い)"
    fi
    continue
  fi

  # それ以外 (5xx / 000 / 404 / 400 等) は FAIL
  echo "  [ng]        ${code} ${ep}"
  fails+=("${ep}=${code}")
done

if [[ "${#fails[@]}" -eq 0 ]]; then
  summary="全 ${#ENDPOINTS[@]} endpoint 到達 OK (env=${ENV_TARGET})"
  if [[ "${#warns[@]}" -gt 0 ]]; then
    summary="${summary}; warn: ${warns[*]}"
  fi
  gate_record PASS "${LABEL}" "${summary}"
  exit 0
fi

gate_record FAIL "${LABEL}" "到達不可: ${fails[*]}"
exit 1
