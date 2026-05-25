#!/usr/bin/env bash
# scripts/cf_pages_check.sh — Cloudflare Pages 公開後の 7 項目 curl チェッカー (P0-5.1)
#
# Asana: P0-5.1 (CF Pages 7 項目 curl チェッカー雛形)
# Related: P0-5 (CF Pages 本番 deploy + WAF / Tunnel)
# Owner: claude.ai/CLI (雛形作成は CLI、本番反映時の閾値調整は人手)
#
# Usage:
#   scripts/cf_pages_check.sh --host app.ultra-auto-trade.com
#   scripts/cf_pages_check.sh --host app.ultra-auto-trade.com --backend-health /health
#   scripts/cf_pages_check.sh --host app.ultra-auto-trade.com --skip 6   # 6番をスキップ
#
# Exit code:
#   0 = 全 7 項目 PASS
#   1 = 1 項目以上 FAIL
#   2 = 引数エラー
#
# 設計方針:
#   - 各チェックは独立、1 項目の失敗で他をスキップしない (全体傾向を一度で見るため)
#   - 終了時に PASS/FAIL を一覧表示し、非ゼロで exit
#   - 外部依存は curl / openssl / awk のみ (busybox 環境でも動くよう grep -E は最小限)

set -uo pipefail

HOST=""
BACKEND_HEALTH="/health"
ASSET_PATH=""           # 空なら /_next/static の最初の js を自動検出
BAD_PATH="/.env"
SKIP_LIST=""
TIMEOUT=10

usage() {
  cat <<'EOF'
Usage: cf_pages_check.sh --host <host> [options]

Options:
  --host <host>             対象 host (必須、例: app.ultra-auto-trade.com)
  --backend-health <path>   3) tunnel reachable で叩く path (default: /health)
  --asset-path <path>       7) cache header チェック対象 (default: 自動検出)
  --bad-path <path>         2) WAF block 想定 path (default: /.env)
  --skip <n[,n,...]>        スキップする項目番号
  --timeout <sec>           curl 各リクエスト timeout (default: 10)
  -h, --help                このヘルプ

7 項目:
  1) TLS handshake (TLS 1.2+ で接続成立、cert 期限 30日以上)
  2) WAF が bad path を 403 でブロック
  3) Tunnel reachable (/<backend-health> が 200 を返す)
  4) Root path が 200
  5) Security headers (HSTS / X-Content-Type-Options / X-Frame-Options)
  6) HTTP -> HTTPS リダイレクト (301 or 308)
  7) Static asset の Cache-Control が public + max-age >= 86400
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)            HOST="$2"; shift 2 ;;
    --backend-health)  BACKEND_HEALTH="$2"; shift 2 ;;
    --asset-path)      ASSET_PATH="$2"; shift 2 ;;
    --bad-path)        BAD_PATH="$2"; shift 2 ;;
    --skip)            SKIP_LIST="$2"; shift 2 ;;
    --timeout)         TIMEOUT="$2"; shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "ERROR: --host is required" >&2
  usage
  exit 2
fi

is_skipped() {
  local n="$1"
  [[ -z "$SKIP_LIST" ]] && return 1
  echo ",${SKIP_LIST}," | grep -q ",${n},"
}

declare -A RESULTS  # idx -> "PASS:msg" or "FAIL:msg" or "SKIP:msg"

set_result() {
  local idx="$1"; local status="$2"; local msg="$3"
  RESULTS[$idx]="${status}:${msg}"
}

# ── 1) TLS handshake + 証明書期限 ────────────────────
check_1_tls() {
  if is_skipped 1; then set_result 1 SKIP "skipped"; return; fi
  local end_date days_left
  if ! end_date=$(echo \
    | timeout "$TIMEOUT" openssl s_client -connect "${HOST}:443" -servername "$HOST" 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2); then
    set_result 1 FAIL "TLS handshake failed"
    return
  fi
  if [[ -z "$end_date" ]]; then
    set_result 1 FAIL "could not read cert enddate"
    return
  fi
  local end_epoch now_epoch
  end_epoch=$(date -d "$end_date" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$end_date" +%s 2>/dev/null || echo 0)
  now_epoch=$(date +%s)
  if [[ "$end_epoch" -eq 0 ]]; then
    set_result 1 FAIL "could not parse enddate: $end_date"
    return
  fi
  days_left=$(( (end_epoch - now_epoch) / 86400 ))
  if [[ "$days_left" -lt 30 ]]; then
    set_result 1 FAIL "cert expires in ${days_left}d (< 30d)"
  else
    set_result 1 PASS "TLS OK, cert ${days_left}d left"
  fi
}

# ── 2) WAF block (bad path → 403) ────────────────────
check_2_waf() {
  if is_skipped 2; then set_result 2 SKIP "skipped"; return; fi
  local code
  code=$(curl -sS -o /dev/null -m "$TIMEOUT" -w "%{http_code}" "https://${HOST}${BAD_PATH}" 2>/dev/null || echo 000)
  if [[ "$code" == "403" ]]; then
    set_result 2 PASS "WAF blocks ${BAD_PATH} (403)"
  elif [[ "$code" == "404" ]]; then
    set_result 2 FAIL "expected 403 (WAF), got 404 (WAF rule missing for ${BAD_PATH})"
  else
    set_result 2 FAIL "expected 403, got ${code}"
  fi
}

# ── 3) Tunnel reachable (/health 200) ───────────────
check_3_tunnel() {
  if is_skipped 3; then set_result 3 SKIP "skipped"; return; fi
  local code
  code=$(curl -sS -o /dev/null -m "$TIMEOUT" -w "%{http_code}" "https://${HOST}${BACKEND_HEALTH}" 2>/dev/null || echo 000)
  if [[ "$code" == "200" ]]; then
    set_result 3 PASS "${BACKEND_HEALTH} -> 200 (tunnel reachable)"
  else
    set_result 3 FAIL "${BACKEND_HEALTH} -> ${code}"
  fi
}

# ── 4) Root path 200 ─────────────────────────────────
check_4_root() {
  if is_skipped 4; then set_result 4 SKIP "skipped"; return; fi
  local code
  code=$(curl -sS -o /dev/null -m "$TIMEOUT" -w "%{http_code}" "https://${HOST}/" 2>/dev/null || echo 000)
  if [[ "$code" == "200" ]]; then
    set_result 4 PASS "/ -> 200"
  else
    set_result 4 FAIL "/ -> ${code}"
  fi
}

# ── 5) Security headers ─────────────────────────────
check_5_security_headers() {
  if is_skipped 5; then set_result 5 SKIP "skipped"; return; fi
  local headers
  headers=$(curl -sS -I -m "$TIMEOUT" "https://${HOST}/" 2>/dev/null || true)
  local missing=()
  echo "$headers" | grep -qi "^strict-transport-security:"     || missing+=("HSTS")
  echo "$headers" | grep -qi "^x-content-type-options:.*nosniff" || missing+=("X-Content-Type-Options")
  echo "$headers" | grep -qi "^x-frame-options:"               || missing+=("X-Frame-Options")
  if [[ ${#missing[@]} -eq 0 ]]; then
    set_result 5 PASS "HSTS + X-CTO + X-Frame-Options present"
  else
    set_result 5 FAIL "missing: ${missing[*]}"
  fi
}

# ── 6) HTTP -> HTTPS redirect ───────────────────────
check_6_redirect() {
  if is_skipped 6; then set_result 6 SKIP "skipped"; return; fi
  local code location
  code=$(curl -sS -o /dev/null -m "$TIMEOUT" -w "%{http_code}" "http://${HOST}/" 2>/dev/null || echo 000)
  location=$(curl -sS -I -m "$TIMEOUT" "http://${HOST}/" 2>/dev/null | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r')
  if [[ "$code" == "301" || "$code" == "308" ]] && [[ "$location" =~ ^https:// ]]; then
    set_result 6 PASS "http -> ${code} ${location}"
  else
    set_result 6 FAIL "expected 301/308 to https, got code=${code} location=${location:-<none>}"
  fi
}

# ── 7) Cache header on static asset ─────────────────
check_7_cache() {
  if is_skipped 7; then set_result 7 SKIP "skipped"; return; fi
  local asset="$ASSET_PATH"
  if [[ -z "$asset" ]]; then
    # Next.js の静的 chunk から最初の 1 個を自動検出
    asset=$(curl -sS -m "$TIMEOUT" "https://${HOST}/" 2>/dev/null \
      | grep -oE '/_next/static/[^"'"'"']+\.js' | head -1 || true)
  fi
  if [[ -z "$asset" ]]; then
    set_result 7 FAIL "no static asset found in / (provide --asset-path)"
    return
  fi
  local cache_hdr max_age
  cache_hdr=$(curl -sS -I -m "$TIMEOUT" "https://${HOST}${asset}" 2>/dev/null \
    | awk 'tolower($1)=="cache-control:"{ $1=""; sub(/^ /,""); print; exit }' | tr -d '\r')
  if [[ -z "$cache_hdr" ]]; then
    set_result 7 FAIL "${asset}: no Cache-Control header"
    return
  fi
  max_age=$(echo "$cache_hdr" | grep -oE 'max-age=[0-9]+' | head -1 | cut -d= -f2)
  if [[ "$cache_hdr" =~ public ]] && [[ -n "$max_age" ]] && [[ "$max_age" -ge 86400 ]]; then
    set_result 7 PASS "${asset}: public, max-age=${max_age}"
  else
    set_result 7 FAIL "${asset}: '${cache_hdr}' (want public + max-age>=86400)"
  fi
}

# ── 実行 ────────────────────────────────────────────
echo "=========================================="
echo "  CF Pages 7-item curl check — ${HOST}"
echo "=========================================="

check_1_tls
check_2_waf
check_3_tunnel
check_4_root
check_5_security_headers
check_6_redirect
check_7_cache

echo ""
printf '%-4s %-5s %s\n' "#" "STAT" "DETAIL"
printf '%-4s %-5s %s\n' "---" "----" "------"

FAIL_COUNT=0
for i in 1 2 3 4 5 6 7; do
  entry="${RESULTS[$i]:-MISS:no result}"
  status="${entry%%:*}"
  msg="${entry#*:}"
  printf '%-4s %-5s %s\n' "$i" "$status" "$msg"
  [[ "$status" == "FAIL" ]] && FAIL_COUNT=$((FAIL_COUNT+1))
done

echo ""
if [[ "$FAIL_COUNT" -eq 0 ]]; then
  echo "✅ ALL CHECKS PASSED (host=${HOST})"
  exit 0
else
  echo "❌ ${FAIL_COUNT} CHECK(S) FAILED (host=${HOST})"
  exit 1
fi
