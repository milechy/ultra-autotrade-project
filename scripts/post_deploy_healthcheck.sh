#!/usr/bin/env bash
# scripts/post_deploy_healthcheck.sh
#
# Gate 8 — deploy 後の外形 healthcheck
# RCA: docs/postmortems/2026-05-09_staging_api_502.md
#
# 目的: 内部 (Hetzner localhost) と外部 (cloudflared 経由 public URL) の両方で
#       deploy 直後に /health 200 + scheduler_healthy=true を確認する。
#       内部だけ確認する従来の deploy_*.sh では「cloudflared ingress port mismatch」型
#       インシデント (2026-05-09) を検知できなかったため Gate 8 として CI に統合。
#
# Usage:
#   ./scripts/post_deploy_healthcheck.sh --env=staging
#   ./scripts/post_deploy_healthcheck.sh --env=production --mode=both
#   HEALTHCHECK_MODE=external CF_ACCESS_CLIENT_ID=... ./scripts/post_deploy_healthcheck.sh --env=staging
#
# Environment variables:
#   HEALTHCHECK_MODE         = internal | external | both (default: internal)
#   HEALTHCHECK_RETRIES      = リトライ回数 (default: 5)
#   HEALTHCHECK_DELAY        = リトライ間隔 秒 (default: 6)
#   CF_ACCESS_CLIENT_ID      = CF Access Service Token Client ID (external/both mode の staging で必須)
#   CF_ACCESS_CLIENT_SECRET  = CF Access Service Token Client Secret (同上)
#   SLACK_WEBHOOK_URL        = 失敗時 Slack 通知先 (省略時は通知なし)
#
# Exit codes:
#   0 = all targets healthy
#   1 = one or more targets failed
#   2 = invalid arguments
#
# 注意:
#   - external mode (staging) は Phase 3b PR-A (2026-05-14 Tunnel + config.yml IaC) 完了までは
#     Service Token 反映問題により 302 を返すため、`HEALTHCHECK_MODE=internal` (default) で運用すること。
#   - PR-A 完了後に CI 側で `HEALTHCHECK_MODE=both` に切替予定。

set -euo pipefail

# ─── Args ───────────────────────────────────────────────────────────
ENV=""
MODE="${HEALTHCHECK_MODE:-internal}"
RETRIES="${HEALTHCHECK_RETRIES:-5}"
DELAY="${HEALTHCHECK_DELAY:-6}"

usage() {
    cat <<'USAGE'
Usage: post_deploy_healthcheck.sh --env=<staging|production> [--mode=<internal|external|both>]

Required:
  --env=staging      または  --env=production

Optional:
  --mode=internal    (default) localhost のみ
  --mode=external    public URL のみ
  --mode=both        内部 + 外部
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --env=*)  ENV="${arg#*=}" ;;
        --mode=*) MODE="${arg#*=}" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $arg" >&2; usage; exit 2 ;;
    esac
done

if [[ -z "$ENV" ]]; then
    echo "ERROR: --env=staging|production is required" >&2
    usage
    exit 2
fi
if [[ "$ENV" != "staging" && "$ENV" != "production" ]]; then
    echo "ERROR: --env must be 'staging' or 'production' (got: $ENV)" >&2
    exit 2
fi
if [[ "$MODE" != "internal" && "$MODE" != "external" && "$MODE" != "both" ]]; then
    echo "ERROR: --mode must be 'internal', 'external', or 'both' (got: $MODE)" >&2
    exit 2
fi

# ─── Endpoint table ─────────────────────────────────────────────────
declare -a INTERNAL_TARGETS
case "$ENV" in
    staging)
        INTERNAL_TARGETS=(
            "blue:http://127.0.0.1:8020/health"
            "green:http://127.0.0.1:8021/health"
            "nginx:http://127.0.0.1:8082/health"
        )
        EXTERNAL_URL="https://api-staging.ultra-auto-trade.com/health"
        EXTERNAL_NEEDS_TOKEN="true"
        ;;
    production)
        INTERNAL_TARGETS=(
            "blue:http://127.0.0.1:8010/health"
            "green:http://127.0.0.1:8011/health"
            "nginx:http://127.0.0.1:8080/health"
        )
        EXTERNAL_URL="https://api.ultra-auto-trade.com/health"
        EXTERNAL_NEEDS_TOKEN="false"
        ;;
esac

failures=()

# ─── Helpers ────────────────────────────────────────────────────────
log() {
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

check_url_status() {
    # $1 = label, $2 = url, $3 = needs CF token (true|false)
    local label="$1"
    local url="$2"
    local need_token="${3:-false}"

    local -a curl_headers=()
    if [[ "$need_token" == "true" ]]; then
        if [[ -z "${CF_ACCESS_CLIENT_ID:-}" || -z "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
            log "  SKIP ${label} (${url}): CF_ACCESS_CLIENT_ID/SECRET not set"
            return 0
        fi
        curl_headers=(
            -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}"
            -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
        )
    fi

    local attempt code
    for attempt in $(seq 1 "$RETRIES"); do
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
                    "${curl_headers[@]}" "$url" 2>/dev/null || echo "000")
        if [[ "$code" == "200" ]]; then
            log "  ✅ ${label}  (${url})  → 200  (attempt ${attempt}/${RETRIES})"
            return 0
        fi
        log "  attempt ${attempt}/${RETRIES}: ${label} → ${code}"
        if [[ "$attempt" -lt "$RETRIES" ]]; then
            sleep "$DELAY"
        fi
    done

    log "  ❌ ${label}  (${url})  → FAILED after ${RETRIES} attempts (last code: ${code})"
    failures+=("${label} (${url})")
    return 1
}

check_scheduler_healthy() {
    # $1 = label, $2 = url, $3 = needs CF token (true|false)
    local label="$1"
    local url="$2"
    local need_token="${3:-false}"

    local -a curl_headers=()
    if [[ "$need_token" == "true" ]]; then
        if [[ -z "${CF_ACCESS_CLIENT_ID:-}" || -z "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
            log "  SKIP scheduler_healthy ${label}: CF_ACCESS_CLIENT_ID/SECRET not set"
            return 0
        fi
        curl_headers=(
            -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}"
            -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
        )
    fi

    local body sched
    body=$(curl -sf --max-time 10 "${curl_headers[@]}" "$url" 2>/dev/null || echo '{}')
    sched=$(echo "$body" | python3 -c \
        "import sys,json; print(json.load(sys.stdin).get('scheduler_healthy','unknown'))" \
        2>/dev/null || echo "unknown")

    case "$sched" in
        True|true)
            log "  ✅ scheduler_healthy=true  (${label})"
            return 0
            ;;
        False|false)
            log "  ❌ scheduler_healthy=false  (${label})"
            failures+=("scheduler_healthy=false at ${label}")
            return 1
            ;;
        *)
            log "  ⚠️  scheduler_healthy=unknown  (${label})  body=${body:0:120}"
            failures+=("scheduler_healthy=unknown at ${label}")
            return 1
            ;;
    esac
}

# ─── Run ────────────────────────────────────────────────────────────
log "=== Gate 8 post-deploy healthcheck ==="
log "    env=${ENV}  mode=${MODE}  retries=${RETRIES}  delay=${DELAY}s"

if [[ "$MODE" == "internal" || "$MODE" == "both" ]]; then
    log "--- Internal targets ---"
    for target in "${INTERNAL_TARGETS[@]}"; do
        label="${target%%:*}"
        url="${target#*:}"
        check_url_status "$label" "$url" "false" || true
    done
    # nginx は scheduler_healthy も確認 (active backend を向いていることを保証)
    nginx_url="${INTERNAL_TARGETS[2]#*:}"
    check_scheduler_healthy "nginx" "$nginx_url" "false" || true
fi

if [[ "$MODE" == "external" || "$MODE" == "both" ]]; then
    log "--- External target (cloudflared 経由) ---"
    check_url_status "external-${ENV}" "$EXTERNAL_URL" "$EXTERNAL_NEEDS_TOKEN" || true
    check_scheduler_healthy "external-${ENV}" "$EXTERNAL_URL" "$EXTERNAL_NEEDS_TOKEN" || true
fi

# ─── Result + Slack ─────────────────────────────────────────────────
if [[ ${#failures[@]} -eq 0 ]]; then
    log "✅ All healthcheck targets passed (env=${ENV} mode=${MODE})"
    exit 0
fi

log "❌ Healthcheck FAILED: ${#failures[@]} target(s)"
for f in "${failures[@]}"; do
    log "    - $f"
done

if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    # JSON-safe: 改行を \n に変換、ダブルクオートをエスケープ
    fail_lines=""
    for f in "${failures[@]}"; do
        escaped=$(echo -n "$f" | sed 's/"/\\"/g')
        fail_lines="${fail_lines}- ${escaped}\\n"
    done
    payload=$(printf '{"text":"❌ *Gate 8 healthcheck FAILED* (env=%s mode=%s)\\n\\n%s\\nSee deploy logs for details. RCA: docs/postmortems/2026-05-09_staging_api_502.md"}' \
        "$ENV" "$MODE" "$fail_lines")
    curl -s -X POST -H "Content-Type: application/json" \
         -d "$payload" "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 \
         || log "  (Slack notification failed)"
fi

exit 1
