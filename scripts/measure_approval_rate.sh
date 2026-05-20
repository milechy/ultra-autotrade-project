#!/usr/bin/env bash
# scripts/measure_approval_rate.sh
#
# Ultra AutoTrade ローンチ条件3: 承認率 (approval_rate) 計測スクリプト
#
# 計測対象: proposals テーブルの status ごとの件数集計
# - approved / executed  → ユーザーが承認した件数
# - rejected             → ユーザーが却下した件数
# - expired / pending    → 応答なし
#
# 使い方:
#   bash scripts/measure_approval_rate.sh                  # production DB
#   STAGING=true bash scripts/measure_approval_rate.sh     # staging DB
#   DAYS=30 bash scripts/measure_approval_rate.sh          # 集計期間 30日
#   SLACK=true bash scripts/measure_approval_rate.sh       # Slack 通知
#   JSON=true bash scripts/measure_approval_rate.sh        # JSON 出力
#
# 環境変数:
#   STAGING           true の場合 staging DB を使用
#   DAYS              集計期間（日数、default: 14）
#   SLACK             true の場合 Slack に結果を送信
#   JSON              true の場合 JSON 形式で stdout に出力
#   ENV_FILE          env ファイルパス (default: /opt/ultra-autotrade/.env.production)

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
STAGING="${STAGING:-false}"
DAYS="${DAYS:-14}"
SLACK="${SLACK:-false}"
JSON="${JSON:-false}"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"

if [[ "$STAGING" == "true" ]]; then
  POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-staging}"
  DB_USER="${DB_USER:-ultra}"
  DB_NAME="${DB_NAME:-ultra_autotrade_staging}"
else
  POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-production}"
  DB_USER="${DB_USER:-ultra}"
  DB_NAME="${DB_NAME:-ultra_autotrade}"
fi

# Slack webhook
_load_slack_webhook() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" && -f "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL=$(grep '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'") || true
  fi
}

_slack_send() {
  local text="$1"
  if [[ "$SLACK" != "true" || -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    return 0
  fi
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$text\"}" > /dev/null 2>&1 || true
}

# =============================================================================
# メイン
# =============================================================================
main() {
  _load_slack_webhook

  local since_date
  since_date=$(date -d "$DAYS days ago" '+%Y-%m-%d' 2>/dev/null || date -v"-${DAYS}d" '+%Y-%m-%d')

  # コンテナ存在確認
  if ! docker ps --filter "name=${POSTGRES_CONTAINER}" --filter "status=running" --format "{{.Names}}" | grep -q .; then
    echo "ERROR: コンテナが見つかりません: $POSTGRES_CONTAINER" >&2
    exit 1
  fi

  # SQL 実行: status ごとの件数、ユーザー別件数
  local result
  result=$(docker exec "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' <<SQL
SELECT
  status,
  COUNT(*) AS cnt,
  COUNT(DISTINCT user_id) AS users
FROM proposals
WHERE created_at >= '$since_date'
GROUP BY status
ORDER BY cnt DESC;
SQL
  )

  # 件数集計
  local approved=0 rejected=0 executed=0 expired=0 pending=0 total=0

  while IFS='|' read -r status cnt _; do
    cnt="${cnt//[[:space:]]/}"
    case "$status" in
      approved) approved=$cnt ;;
      rejected) rejected=$cnt ;;
      executed) executed=$cnt ;;
      expired)  expired=$cnt ;;
      pending)  pending=$cnt ;;
    esac
  done <<< "$result"

  total=$(( approved + rejected + executed + expired + pending ))
  local decided=$(( approved + rejected + executed ))  # 応答あり

  # 承認率計算
  local approval_rate_pct="0.0"
  local response_rate_pct="0.0"
  if [[ $total -gt 0 ]]; then
    response_rate_pct=$(awk "BEGIN {printf \"%.1f\", ($decided / $total) * 100}")
  fi
  if [[ $decided -gt 0 ]]; then
    approval_rate_pct=$(awk "BEGIN {printf \"%.1f\", (($approved + $executed) / $decided) * 100}")
  fi

  # ユーザー別サマリ (承認率 > 0 のユーザー)
  local user_summary
  user_summary=$(docker exec "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' <<SQL
SELECT
  p.user_id,
  u.email,
  COUNT(*) FILTER (WHERE p.status IN ('approved','executed')) AS ok,
  COUNT(*) FILTER (WHERE p.status = 'rejected') AS ng,
  COUNT(*) AS total
FROM proposals p
LEFT JOIN users u ON u.id = p.user_id
WHERE p.created_at >= '$since_date'
GROUP BY p.user_id, u.email
ORDER BY ok DESC
LIMIT 10;
SQL
  )

  if [[ "$JSON" == "true" ]]; then
    # JSON 出力
    printf '{
  "period_days": %d,
  "since": "%s",
  "total": %d,
  "approved": %d,
  "executed": %d,
  "rejected": %d,
  "expired": %d,
  "pending": %d,
  "approval_rate_pct": %s,
  "response_rate_pct": %s,
  "environment": "%s"
}\n' \
      "$DAYS" "$since_date" "$total" \
      "$approved" "$executed" "$rejected" "$expired" "$pending" \
      "$approval_rate_pct" "$response_rate_pct" \
      "${STAGING:+staging}"
    return 0
  fi

  # テキスト出力
  echo ""
  echo "=========================================="
  echo " Approval Rate — 過去 ${DAYS} 日間 (${since_date}〜)"
  if [[ "$STAGING" == "true" ]]; then
    echo " 環境: staging"
  else
    echo " 環境: production"
  fi
  echo "=========================================="
  echo ""
  echo "  提案総数:      $total 件"
  echo "  承認/実行:     $(( approved + executed )) 件  (approved: $approved / executed: $executed)"
  echo "  却下:          $rejected 件"
  echo "  期限切れ:      $expired 件"
  echo "  応答待ち:      $pending 件"
  echo ""
  echo "  応答率:        ${response_rate_pct}%  (応答あり / 総数)"
  echo "  承認率:        ${approval_rate_pct}%  (承認+実行 / 応答あり)"
  echo ""

  if [[ -n "$user_summary" ]]; then
    echo "  ユーザー別 (上位10):"
    printf "  %-4s %-30s %6s %6s %6s\n" "ID" "Email" "承認" "却下" "合計"
    printf "  %s\n" "$(printf '%.0s-' {1..60})"
    while IFS='|' read -r uid email ok ng tot; do
      printf "  %-4s %-30s %6s %6s %6s\n" "$uid" "${email:-unknown}" "$ok" "$ng" "$tot"
    done <<< "$user_summary"
    echo ""
  fi

  # ローンチ条件3の評価
  echo "  ローンチ条件3 評価:"
  local launch_ok=true
  if (( total == 0 )); then
    echo "  ⚠️  提案数 0 件 — 観測期間の延長が必要"
    launch_ok=false
  elif awk "BEGIN {exit ($approval_rate_pct >= 60) ? 0 : 1}"; then
    echo "  ✅ 承認率 ${approval_rate_pct}% ≥ 60% — 条件クリア"
  else
    echo "  ❌ 承認率 ${approval_rate_pct}% < 60% — 条件未達"
    launch_ok=false
  fi
  echo ""

  # Slack 通知
  if [[ "$SLACK" == "true" ]]; then
    local emoji="✅"
    [[ "$launch_ok" != "true" ]] && emoji="⚠️"
    _slack_send "${emoji} *承認率レポート (${DAYS}日間)* — 承認率: ${approval_rate_pct}% | 応答率: ${response_rate_pct}% | 提案数: ${total}"
  fi
}

main "$@"
