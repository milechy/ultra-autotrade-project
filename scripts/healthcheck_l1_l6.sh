#!/usr/bin/env bash
# scripts/healthcheck_l1_l6.sh
#
# Ultra AutoTrade L1-L6 自動ヘルスチェック (5分間隔 cron)
#
# PASS時: 1時間に1回通知 (/tmp/.last_healthcheck_pass タイムスタンプで管理)
# FAIL時: 即通知
# L6 FAIL: UAT期間中は常態化、warn扱い (エスカレーション対象外)
#
# 使用例:
#   ./scripts/healthcheck_l1_l6.sh          # 通常実行
#   DRY_RUN=true ./scripts/healthcheck_l1_l6.sh  # Slack送信をスキップしてJSONを表示
#
# cron登録例 (Hetzner /opt/ultra-autotrade/scripts/ に配置後):
#   */5 * * * * /opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh >> /opt/ultra-autotrade/logs/healthcheck_l1_l6.log 2>&1

set -uo pipefail

# ============================================================
# 設定
# ============================================================
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
PASS_STAMP_FILE="${PASS_STAMP_FILE:-/tmp/.last_healthcheck_pass}"
LOG_DIR="${LOG_DIR:-/opt/ultra-autotrade/logs}"
TIMEOUT="${TIMEOUT:-10}"
DRY_RUN="${DRY_RUN:-false}"

POSTGRES_CONTAINER="ultra-autotrade-postgres-production"
DB_USER="ultra"
DB_NAME="ultra_autotrade"
BACKEND_BLUE_URL="http://127.0.0.1:8010"
BACKEND_PUBLIC_URL="https://api.ultra-auto-trade.com"

# 期待する常時起動コンテナ (7台)
REQUIRED_CONTAINERS=(
  "ultra-autotrade-loki-production"
  "ultra-autotrade-promtail-production"
  "ultra-autotrade-postgres-production"
  "ultra-autotrade-backend-blue-production"
  "ultra-autotrade-nginx-production"
  "ultra-autotrade-cloudflared-production"
  "ultra-autotrade-frontend-production"
)

# env ファイルから Slack Webhook を取得
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
if [[ -z "$SLACK_WEBHOOK_URL" && -f "$ENV_FILE" ]]; then
  SLACK_WEBHOOK_URL="$(grep '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2-)"
fi

mkdir -p "$LOG_DIR"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
NEXT_CHECK="$(date -u -d "+5 minutes" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")"

# ============================================================
# ユーティリティ
# ============================================================
run_psql() {
  docker exec "$POSTGRES_CONTAINER" \
    psql -U "$DB_USER" -d "$DB_NAME" -tAc "$1" 2>/dev/null || echo ""
}

# ============================================================
# L1: インフラチェック
# ============================================================
check_l1() {
  local status="PASS"
  local details=""
  local failed=()

  for c in "${REQUIRED_CONTAINERS[@]}"; do
    local running
    running="$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo "false")"
    if [[ "$running" != "true" ]]; then
      failed+=("$c")
    fi
  done

  if [[ ${#failed[@]} -gt 0 ]]; then
    status="FAIL"
    details="containers down: $(IFS=','; echo "${failed[*]}")"
  fi

  # 内部 /health (backend-blue)
  local local_code
  local_code="$(curl -sf -o /dev/null -w "%{http_code}" \
    --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    "$BACKEND_BLUE_URL/health" 2>/dev/null || echo "000")"
  if [[ "$local_code" != "200" ]]; then
    status="FAIL"
    details="${details:+$details; }local /health HTTP $local_code"
  fi

  # 外形 /health (Cloudflare経由)
  local pub_code
  pub_code="$(curl -sf -o /dev/null -w "%{http_code}" \
    --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    "$BACKEND_PUBLIC_URL/health" 2>/dev/null || echo "000")"
  if [[ "$pub_code" != "200" ]]; then
    status="FAIL"
    details="${details:+$details; }public /health HTTP $pub_code"
  fi

  [[ "$status" == "PASS" ]] && details="all ${#REQUIRED_CONTAINERS[@]} containers up, /health 200"
  printf '{"status":"%s","details":"%s"}' "$status" "$details"
}

# ============================================================
# L2: スケジューラーチェック
# ============================================================
check_l2() {
  local status="PASS"
  local details=""
  local scheduler_healthy="false"
  local last_age_min=0

  local body
  body="$(curl -sf --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    "$BACKEND_BLUE_URL/health" 2>/dev/null || echo "{}")"

  scheduler_healthy="$(echo "$body" | jq -r '.scheduler_healthy // .scheduler // false' 2>/dev/null || echo "false")"
  local last_judgment
  last_judgment="$(echo "$body" | jq -r '.last_judgment // empty' 2>/dev/null || echo "")"
  local warnings_count
  warnings_count="$(echo "$body" | jq '.warnings | length // 0' 2>/dev/null || echo 0)"

  if [[ "$scheduler_healthy" != "true" ]]; then
    status="FAIL"
    details="scheduler_healthy=$scheduler_healthy"
  fi

  if [[ -n "$last_judgment" ]]; then
    local now_epoch lj_epoch
    now_epoch="$(date +%s)"
    lj_epoch="$(date -d "$last_judgment" +%s 2>/dev/null || echo "$now_epoch")"
    last_age_min=$(( (now_epoch - lj_epoch) / 60 ))
    if [[ $last_age_min -gt 60 ]]; then
      status="FAIL"
      details="${details:+$details; }last_judgment ${last_age_min}min ago (>60)"
    fi
  fi

  if [[ "$warnings_count" -gt 0 ]]; then
    status="FAIL"
    local warnings_text
    warnings_text="$(echo "$body" | jq -r '.warnings[]' 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
    details="${details:+$details; }warnings: $warnings_text"
  fi

  [[ "$status" == "PASS" ]] && details="scheduler_healthy=true, last_judgment ${last_age_min}min ago"
  local sh_bool
  [[ "$scheduler_healthy" == "true" ]] && sh_bool="true" || sh_bool="false"
  printf '{"status":"%s","scheduler_healthy":%s,"last_judgment_age_min":%d,"details":"%s"}' \
    "$status" "$sh_bool" "$last_age_min" "$details"
}

# ============================================================
# L3: AI判定チェック (24h >= 3件)
# ============================================================
check_l3() {
  local status="PASS"
  local count
  count="$(run_psql "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';" | tr -d '[:space:]')"
  count="${count:-0}"
  [[ "$count" -lt 3 ]] && status="FAIL"
  printf '{"status":"%s","ai_decisions_24h":%s}' "$status" "$count"
}

# ============================================================
# L4: ユーザー反応チェック (proposals expired率 < 0.5)
# ============================================================
check_l4() {
  local status="PASS"
  local expired_rate="0.00"

  local result
  result="$(run_psql "SELECT COUNT(*), COUNT(*) FILTER (WHERE status='expired') FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';")"
  result="$(echo "$result" | tr -d '[:space:]')"

  local total="${result%%|*}"
  local expired="${result##*|}"
  total="${total:-0}"
  expired="${expired:-0}"

  if [[ "$total" -gt 0 ]]; then
    expired_rate="$(awk "BEGIN {printf \"%.2f\", $expired / $total}")"
    if awk "BEGIN {exit !($expired_rate >= 0.5)}"; then
      status="FAIL"
    fi
  fi

  printf '{"status":"%s","proposals_24h":%s,"expired_rate":%s}' \
    "$status" "$total" "$expired_rate"
}

# ============================================================
# L5: 実取引チェック (tx_hash NULL率 < 0.2)
# ============================================================
check_l5() {
  local status="PASS"

  local result
  result="$(run_psql "SELECT COUNT(*), COUNT(*) FILTER (WHERE tx_hash IS NULL AND is_dry_run = false) FROM transactions WHERE created_at > NOW() - INTERVAL '24 hours';")"
  result="$(echo "$result" | tr -d '[:space:]')"

  local total="${result%%|*}"
  local failed="${result##*|}"
  total="${total:-0}"
  failed="${failed:-0}"

  if [[ "$total" -gt 0 && "$failed" -gt 0 ]]; then
    local fail_rate
    fail_rate="$(awk "BEGIN {printf \"%.2f\", $failed / $total}")"
    if awk "BEGIN {exit !($fail_rate >= 0.2)}"; then
      status="FAIL"
    fi
  fi

  printf '{"status":"%s","tx_24h":%s,"tx_failed_24h":%s}' "$status" "$total" "$failed"
}

# ============================================================
# L6: 収益チェック (zero_value < 50%, UAT期間中はWARN)
# ============================================================
check_l6() {
  local status="PASS"
  local zero_pct=0

  local result
  result="$(run_psql "SELECT COUNT(*), COUNT(*) FILTER (WHERE total_value_usd = 0 OR total_value_usd IS NULL) FROM portfolio_snapshots WHERE recorded_at > NOW() - INTERVAL '1 day';")"
  result="$(echo "$result" | tr -d '[:space:]')"

  local total="${result%%|*}"
  local zero_count="${result##*|}"
  total="${total:-0}"
  zero_count="${zero_count:-0}"

  if [[ "$total" -gt 0 ]]; then
    zero_pct="$(awk "BEGIN {printf \"%d\", $zero_count / $total * 100}")"
    if [[ "$zero_pct" -ge 50 ]]; then
      status="WARN"
    fi
  fi

  local note
  [[ "$status" == "WARN" ]] && note="UAT期間中常態化" || note="ok"
  printf '{"status":"%s","zero_value_pct":%d,"note":"%s"}' "$status" "$zero_pct" "$note"
}

# ============================================================
# Slack 通知
# ============================================================
send_slack() {
  local payload="$1"

  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "[WARN] SLACK_WEBHOOK_URL not set, skipping notification" >&2
    return 0
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY_RUN] Would send to Slack:" >&2
    echo "$payload" | jq . >&2
    return 0
  fi

  local slack_text
  slack_text="$(echo "$payload" | jq -c '@json')"
  curl -sf -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": $slack_text}" >/dev/null 2>&1 || \
    echo "[WARN] Slack notification failed" >&2
}

# ============================================================
# メイン
# ============================================================
main() {
  local l1 l2 l3 l4 l5 l6
  l1="$(check_l1)"
  l2="$(check_l2)"
  l3="$(check_l3)"
  l4="$(check_l4)"
  l5="$(check_l5)"
  l6="$(check_l6)"

  # L6 WARNは全体FAILにしない (UAT期間中の常態)
  local overall="PASS"
  for result in "$l1" "$l2" "$l3" "$l4" "$l5"; do
    if echo "$result" | jq -e '.status == "FAIL"' >/dev/null 2>&1; then
      overall="FAIL"
      break
    fi
  done

  local payload
  payload="$(jq -nc \
    --arg task "healthcheck_l1_l6" \
    --arg status "$overall" \
    --arg ts "$TIMESTAMP" \
    --arg next "$NEXT_CHECK" \
    --argjson l1 "$l1" \
    --argjson l2 "$l2" \
    --argjson l3 "$l3" \
    --argjson l4 "$l4" \
    --argjson l5 "$l5" \
    --argjson l6 "$l6" \
    '{
      task: $task,
      status: $status,
      timestamp: $ts,
      results: {L1: $l1, L2: $l2, L3: $l3, L4: $l4, L5: $l5, L6: $l6},
      next_check: $next
    }')"

  echo "$payload"

  # 通知ポリシー
  if [[ "$overall" == "FAIL" ]]; then
    send_slack "$payload"
  else
    local now_epoch last_pass elapsed
    now_epoch="$(date +%s)"
    last_pass="$(cat "$PASS_STAMP_FILE" 2>/dev/null || echo 0)"
    elapsed=$(( now_epoch - last_pass ))
    if [[ $elapsed -ge 3600 ]]; then
      send_slack "$payload"
      echo "$now_epoch" > "$PASS_STAMP_FILE"
    fi
  fi
}

main "$@"
