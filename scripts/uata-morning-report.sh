#!/bin/bash
# UATa Morning Report - 朝6:00 cron で実行
# 配置先: scripts/uata-morning-report.sh
# 用途: 夜間の自走結果を Slack DM + Pushover Lowest で報告

set -uo pipefail

UATA_ROOT="${UATA_ROOT:-$HOME/projects/ultra-autotrade}"
UATA_CONFIG="${UATA_CONFIG:-$HOME/.claude-uata}"
QUEUE_DB="$UATA_ROOT/.claude/queue/uata-queue.db"
LOG="$UATA_CONFIG/logs/morning-report.log"

mkdir -p "$(dirname $LOG)"
exec >> "$LOG" 2>&1

source "$UATA_CONFIG/load-env.sh" 2>/dev/null || true
source "$UATA_ROOT/scripts/uata-pushover-notify.sh" 2>/dev/null || true

DATE=$(date +%Y-%m-%d)
HOUR=$(date +%H)
echo "[$(date +%Y-%m-%d_%H:%M:%S)] === Morning Report Start ==="

# ─── 1. 夜間の自動完了 PR 一覧 ───

LAST_REPORT=$(SQ "SELECT value FROM automation_state WHERE key = 'last_morning_report';")
[ -z "$LAST_REPORT" ] || [ "$LAST_REPORT" = "1970-01-01T00:00:00Z" ] && LAST_REPORT=$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "yesterday" +%Y-%m-%dT%H:%M:%SZ)

AUTO_DONE=$(SQ "
SELECT 'PR ' || pr_number || ': [Tier ' || tier || '] ' || substr(asana_name, 1, 60) AS line
FROM tasks
WHERE state = 'done'
  AND updated_at > '$LAST_REPORT'
ORDER BY tier, updated_at DESC
LIMIT 20;
")
AUTO_DONE_COUNT=$( [ -n "$AUTO_DONE" ] && printf '%s\n' "$AUTO_DONE" | grep -c '^' || echo 0 )

# ─── 2. 承認待ち Tier A ───

PENDING_A=$(SQ "
SELECT '#' || pr_number || ' ' || substr(asana_name, 1, 60) AS line
FROM tasks
WHERE state = 'needs_approval' AND tier = 'A'
ORDER BY created_at ASC
LIMIT 10;
")
PENDING_A_COUNT=$( [ -n "$PENDING_A" ] && printf '%s\n' "$PENDING_A" | grep -c '^' || echo 0 )

# ─── 3. 承認待ち Tier S (Critical) ───

PENDING_S=$(SQ "
SELECT '#' || pr_number || ' ' || substr(asana_name, 1, 60) AS line
FROM tasks
WHERE state = 'needs_approval_critical' AND tier = 'S'
ORDER BY created_at ASC
LIMIT 10;
")
PENDING_S_COUNT=$( [ -n "$PENDING_S" ] && printf '%s\n' "$PENDING_S" | grep -c '^' || echo 0 )

# ─── 4. 失敗 (rollback済) ───

FAILED=$(SQ "
SELECT 'Task ' || id || ': ' || substr(asana_name, 1, 60) || ' (' || COALESCE(error_message, '?') || ')' AS line
FROM tasks
WHERE state IN ('failed', 'rollbacked')
  AND updated_at > '$LAST_REPORT'
ORDER BY updated_at DESC
LIMIT 5;
")
FAILED_COUNT=$( [ -n "$FAILED" ] && printf '%s\n' "$FAILED" | grep -c '^' || echo 0 )

# ─── 5. L1-L6 状態 ───
# 本番ログ出力先: /opt/ultra-autotrade/logs/healthcheck_l1_l6.log (id=30 で修正)
# fallback: SSH 取得失敗時は curl /health HTTP ステータスで代替 (PR #246 維持)
SSH_OPTS=(-F /dev/null -i ~/.ssh/hetzner_assistone_production -o IdentitiesOnly=yes
          -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10)

HEALTH_RAW=$(ssh "${SSH_OPTS[@]}" root@5.223.88.14 \
    'tail -1 /opt/ultra-autotrade/logs/healthcheck_l1_l6.log 2>/dev/null' 2>/dev/null)
if [ -n "$HEALTH_RAW" ]; then
    HEALTH="$HEALTH_RAW"
else
    HC=$(curl -fsS --max-time 10 -o /dev/null -w "%{http_code}" \
         https://api.ultra-auto-trade.com/health 2>/dev/null || echo "fail")
    HEALTH="(L1-L6 ログ取得失敗 / L1 外形 /health HTTP=${HC})"
fi


# ─── 6. 山本さん UAT 状況 (R3: 正ロール=ultra。heredoc で $$ 安全化) ───

YAMAMOTO_STATUS=$(ssh "${SSH_OPTS[@]}" root@5.223.88.14 bash -s <<'ENDSSH' 2>/dev/null
PG_CONTAINER=$(docker ps --filter 'name=postgres-production' --filter 'status=running' --format '{{.Names}}' | head -1)
if [ -z "$PG_CONTAINER" ]; then
  echo "(postgres-production コンテナが見つかりません)"
else
  docker exec "$PG_CONTAINER" \
    psql -U ultra -d ultra_autotrade -t -A -F'|' -c \
    "SELECT
       (SELECT COUNT(*) FROM proposals    WHERE user_id=11 AND status='pending'),
       (SELECT COUNT(*) FROM transactions WHERE user_id=11),
       (SELECT MAX(created_at) FROM proposals WHERE user_id=11);"
fi
ENDSSH
)
[ -z "$YAMAMOTO_STATUS" ] && YAMAMOTO_STATUS="(取得失敗)"

# ─── 7. mode 確認 ───

CURRENT_MODE=$(SQ "SELECT value FROM automation_state WHERE key = 'mode';")

# ─── 8. レポート組立て ───

REPORT_BODY=$(cat <<EOF
🌅 *UATa Morning Report ${DATE}*

📊 *自走結果サマリ* (前回レポートから)
- ✅ 自動完了: ${AUTO_DONE_COUNT} PR
- ⚠️ Tier A 承認待ち: ${PENDING_A_COUNT} 件
- 🔴 Tier S 承認待ち: ${PENDING_S_COUNT} 件
- ❌ 失敗(rollback済): ${FAILED_COUNT} 件
- 🌙 night-mode: ${CURRENT_MODE}

EOF
)

if [ "$AUTO_DONE_COUNT" -gt 0 ]; then
    REPORT_BODY+=$'\n*完了 PR:*\n'"$AUTO_DONE"$'\n'
fi

if [ "$PENDING_A_COUNT" -gt 0 ]; then
    REPORT_BODY+=$'\n*Tier A 承認待ち:*\n'"$PENDING_A"$'\n'
fi

if [ "$PENDING_S_COUNT" -gt 0 ]; then
    REPORT_BODY+=$'\n*🔴 Tier S 承認待ち (claude.ai 相談推奨):*\n'"$PENDING_S"$'\n'
fi

if [ "$FAILED_COUNT" -gt 0 ]; then
    REPORT_BODY+=$'\n*失敗 (rollback済):*\n'"$FAILED"$'\n'
fi

REPORT_BODY+=$'\n*L1-L6:*\n'"$HEALTH"$'\n'

REPORT_BODY+=$'\n*🤝 山本さん UAT:*\n'"$YAMAMOTO_STATUS"$'\n'

REPORT_BODY+=$'\n----\nApprove/reject from Slack thread or visit https://github.com/milechy/ultra-autotrade-project/pulls\n'

echo "$REPORT_BODY"

# ─── 9. Slack DM 送信 ───

if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
    SLACK_PAYLOAD=$(jq -nc \
        --arg text "$REPORT_BODY" \
        '{ "text": $text, "mrkdwn": true }')
    
    curl -s -X POST -H "Content-Type: application/json" \
         -d "$SLACK_PAYLOAD" "$SLACK_WEBHOOK_URL" > /dev/null
    echo "Sent to Slack webhook"
fi

# ─── 10. Pushover Lowest (priority=-2) ───

# 重要度に応じて優先度調整: Tier S 承認待ちあれば High、それ以外は Lowest
if [ "$PENDING_S_COUNT" -gt 0 ]; then
    uata_notify_high "UATa Morning ${DATE}" \
        "${PENDING_S_COUNT} Tier S awaiting approval, ${PENDING_A_COUNT} Tier A, ${AUTO_DONE_COUNT} done" \
        "https://github.com/milechy/ultra-autotrade-project/pulls" 2>/dev/null || true
elif [ "$FAILED_COUNT" -ge 3 ]; then
    uata_notify_high "UATa Morning ${DATE}" \
        "${FAILED_COUNT} failed tasks need attention" 2>/dev/null || true
else
    # priority=-2 (Lowest, sound 鳴らない)
    curl -s --form-string "token=${PUSHOVER_APP_TOKEN:-}" \
         --form-string "user=${PUSHOVER_USER_KEY:-}" \
         --form-string "title=UATa Morning ${DATE}" \
         --form-string "message=${AUTO_DONE_COUNT} done, ${PENDING_A_COUNT} A, ${PENDING_S_COUNT} S, ${FAILED_COUNT} failed" \
         --form-string "priority=-2" \
         "https://api.pushover.net/1/messages.json" > /dev/null
fi

# ─── 11. State 更新 ───

SQ "UPDATE automation_state SET value = '$(date -u +%Y-%m-%dT%H:%M:%SZ)' WHERE key = 'last_morning_report';"

# ─── 12. notification log ───

SQ "INSERT INTO notifications (task_id, notification_type, payload) VALUES (NULL, 'morning_report', 'sent $(date -u +%Y-%m-%dT%H:%M:%SZ) - ${AUTO_DONE_COUNT} done');"

echo "[$(date +%Y-%m-%d_%H:%M:%S)] === Morning Report Done ==="
echo ""
