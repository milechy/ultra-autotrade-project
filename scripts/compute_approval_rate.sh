#!/usr/bin/env bash
# compute_approval_rate.sh — proposals の承認率を計測して Slack に投稿
# 本番 DB read-only。テストデータ投入なし。
# 実行: ./scripts/compute_approval_rate.sh [--days N] [--quiet]

set -euo pipefail

COMPOSE_DIR="/opt/ultra-autotrade"
WEBHOOK_FILE="${COMPOSE_DIR}/.env.production"
DAYS="${1:-7}"
QUIET=false

# --days / --quiet オプション解析
for arg in "$@"; do
  case "$arg" in
    --days) shift; DAYS="$1" ;;
    --days=*) DAYS="${arg#*=}" ;;
    --quiet) QUIET=true ;;
  esac
done

PG_CONTAINER="ultra-autotrade-postgres-production"
PG_USER="ultra"
PG_DB="ultra_autotrade"

pg() {
  docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -t -c "$1" 2>/dev/null
}

# 集計
APPROVED=$(pg "SELECT COUNT(*) FROM proposals WHERE status='approved' AND created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ')
REJECTED=$(pg "SELECT COUNT(*) FROM proposals WHERE status='rejected' AND created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ')
EXPIRED=$(pg "SELECT COUNT(*) FROM proposals WHERE status='expired' AND created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ')
PENDING=$(pg "SELECT COUNT(*) FROM proposals WHERE status='pending' AND created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ')
TOTAL=$((APPROVED + REJECTED + EXPIRED))

if [[ "${TOTAL}" -eq 0 ]]; then
  RATE="N/A (完了提案なし)"
else
  RATE=$(awk "BEGIN {printf \"%.1f%%\", ${APPROVED} / ${TOTAL} * 100}")
fi

# v4 vs v3 内訳
V4_COUNT=$(pg "SELECT COUNT(*) FROM proposals p JOIN ai_decisions d ON p.ai_decision_id=d.id WHERE d.prompt_version='v4' AND p.created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ' 2>/dev/null || echo "N/A")
V3_COUNT=$(pg "SELECT COUNT(*) FROM proposals p JOIN ai_decisions d ON p.ai_decision_id=d.id WHERE d.prompt_version='v3' AND p.created_at > NOW() - INTERVAL '${DAYS} days';" | tr -d ' ' 2>/dev/null || echo "N/A")

REPORT="📊 approval_rate レポート (直近 ${DAYS}日)
承認: ${APPROVED}件 / 却下: ${REJECTED}件 / 期限切れ: ${EXPIRED}件 / 承認待ち: ${PENDING}件
承認率: ${RATE}
prompt_version 内訳: v4=${V4_COUNT}件 / v3以前=${V3_COUNT}件"

echo "${REPORT}"

if [[ "${QUIET}" = false ]]; then
  WEBHOOK=$(grep "^SLACK_WEBHOOK_URL=" "${WEBHOOK_FILE}" 2>/dev/null | cut -d= -f2- || true)
  if [[ -n "${WEBHOOK}" ]]; then
    curl -sf -X POST "${WEBHOOK}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${REPORT}\"}" >/dev/null 2>&1 || true
    echo "[slack] 投稿完了"
  fi
fi
