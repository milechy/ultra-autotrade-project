#!/usr/bin/env bash
# lane-complete-handler.sh — Stop event で DoD 判定 + queue.db 更新 + Slack 通知
#
# 呼び出し: hooks.Stop に登録、stdin に Claude Code の Stop event JSON が入る
# 対象: queue.db で state='running' のタスクに session_id が一致するレコード
#
# DoD 判定ロジック:
#   PR 発見 (gh pr list --head <branch>)  → state=pr_created, pr_number/pr_url 記録
#   PR なし + verify.sh 最近 pass の証跡  → state=failed, attempt_count+1
#   running タスクが見当たらない           → 静かに exit 0 (Lane 外のセッション)

set -euo pipefail

QUEUE_DB="${QUEUE_DB:-$(git rev-parse --show-toplevel 2>/dev/null)/.claude/queue/uata-queue.db}"
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"

# ---------- stdin parse ----------
STDIN_DATA=""
if ! tty -s 2>/dev/null; then
  STDIN_DATA=$(cat)
fi

SESSION_ID=""
if [[ -n "$STDIN_DATA" ]]; then
  SESSION_ID=$(printf '%s' "$STDIN_DATA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('session_id', ''))
except Exception:
    print('')
" 2>/dev/null || true)
fi

# 環境変数フォールバック
SESSION_ID="${SESSION_ID:-${CLAUDE_SESSION_ID:-}}"

if [[ -z "$SESSION_ID" ]]; then
  # session_id が特定できない → 処理スキップ
  exit 0
fi

# ---------- queue.db が存在しない場合はスキップ ----------
if [[ ! -f "$QUEUE_DB" ]]; then
  exit 0
fi

# ---------- 対象タスク検索 ----------
TASK_ROW=$(sqlite3 "$QUEUE_DB" "
  SELECT t.id, t.asana_name, t.tier, t.branch, t.state, t.attempt_count
  FROM tasks t
  LEFT JOIN lane_pool p ON p.task_id = t.id
  WHERE (t.session_id = '$SESSION_ID' OR p.session_id = '$SESSION_ID')
    AND t.state = 'running'
  LIMIT 1;
" 2>/dev/null || true)

if [[ -z "$TASK_ROW" ]]; then
  # 対応する running タスクなし → Lane 外セッションの停止
  exit 0
fi

TASK_ID=$(printf '%s' "$TASK_ROW" | cut -d'|' -f1)
TASK_NAME=$(printf '%s' "$TASK_ROW" | cut -d'|' -f2)
TIER=$(printf '%s' "$TASK_ROW" | cut -d'|' -f3)
TASK_BRANCH=$(printf '%s' "$TASK_ROW" | cut -d'|' -f4)
CURRENT_STATE=$(printf '%s' "$TASK_ROW" | cut -d'|' -f5)
ATTEMPT_COUNT=$(printf '%s' "$TASK_ROW" | cut -d'|' -f6)

# ブランチ名: tasks.branch が空ならカレント HEAD
BRANCH="${TASK_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}"

# ---------- PR 有無を確認 ----------
PR_NUMBER=""
PR_URL=""

if [[ -n "$BRANCH" ]] && command -v gh &>/dev/null; then
  PR_JSON=$(gh pr list --head "$BRANCH" --state open --json number,url --limit 1 2>/dev/null || echo "[]")
  if [[ "$PR_JSON" != "[]" && -n "$PR_JSON" ]]; then
    PR_NUMBER=$(printf '%s' "$PR_JSON" | python3 -c "
import sys, json
try:
    rows = json.load(sys.stdin)
    print(rows[0]['number'] if rows else '')
except Exception:
    print('')
" 2>/dev/null || true)
    PR_URL=$(printf '%s' "$PR_JSON" | python3 -c "
import sys, json
try:
    rows = json.load(sys.stdin)
    print(rows[0]['url'] if rows else '')
except Exception:
    print('')
" 2>/dev/null || true)
  fi
fi

# ---------- DoD 判定 ----------
if [[ -n "$PR_NUMBER" ]]; then
  # PR 存在 → DoD 達成
  NEW_STATE="pr_created"

  # Tier B は人間承認なしにマージしないが、CI 全 pass なら ready_to_merge に昇格
  if [[ "$TIER" == "B" ]]; then
    CI_CHECKS=$(gh pr checks "$PR_NUMBER" --json state --jq '[.[].state] | unique | .[]' 2>/dev/null || echo "")
    if [[ "$CI_CHECKS" == "SUCCESS" ]]; then
      NEW_STATE="ready_to_merge"
    fi
  fi

  # queue.db 更新 (pr_number / pr_url / state / completed_at)
  sqlite3 "$QUEUE_DB" "
    UPDATE tasks
    SET state       = '$NEW_STATE',
        pr_number   = $PR_NUMBER,
        pr_url      = '$PR_URL',
        completed_at = CURRENT_TIMESTAMP,
        last_action  = 'stop_hook: PR=$PR_NUMBER found → $NEW_STATE'
    WHERE id = $TASK_ID;
  " 2>/dev/null

  # lane_pool から解放
  sqlite3 "$QUEUE_DB" "DELETE FROM lane_pool WHERE task_id = $TASK_ID;" 2>/dev/null

  SLACK_STATUS="success"
  SLACK_MSG="✅ Lane 完了 (PR #${PR_NUMBER}): ${TASK_NAME}"
else
  # PR なし → DoD 未達成
  NEW_ATTEMPT=$((ATTEMPT_COUNT + 1))
  MAX_ATTEMPTS=$(sqlite3 "$QUEUE_DB" "SELECT max_attempts FROM tasks WHERE id=$TASK_ID;" 2>/dev/null || echo "3")

  if [[ "$NEW_ATTEMPT" -ge "$MAX_ATTEMPTS" ]]; then
    FINAL_STATE="failed"
    SLACK_STATUS="failure"
    SLACK_MSG="❌ Lane 失敗 (試行 ${NEW_ATTEMPT}/${MAX_ATTEMPTS}, PR なし): ${TASK_NAME}"
  else
    FINAL_STATE="pending"
    SLACK_STATUS="partial"
    SLACK_MSG="⚠️ Lane 未完了 (試行 ${NEW_ATTEMPT}/${MAX_ATTEMPTS}, PR なし): ${TASK_NAME}"
  fi

  sqlite3 "$QUEUE_DB" "
    UPDATE tasks
    SET state         = '$FINAL_STATE',
        attempt_count = $NEW_ATTEMPT,
        last_action   = 'stop_hook: no PR found → $FINAL_STATE (attempt $NEW_ATTEMPT)'
    WHERE id = $TASK_ID;
  " 2>/dev/null

  sqlite3 "$QUEUE_DB" "DELETE FROM lane_pool WHERE task_id = $TASK_ID;" 2>/dev/null
fi

# ---------- Slack 通知 ----------
# send-lane-completion.sh が存在すれば委譲
SEND_LANE_SH="${HOOKS_DIR}/send-lane-completion.sh"
if [[ -x "$SEND_LANE_SH" ]]; then
  "${SEND_LANE_SH}" \
    "${BRANCH:-unknown}" \
    "auto-stop" \
    "${SLACK_STATUS}" \
    "${PR_URL:-}" \
    "" \
    "" \
    "${TIER:-}" \
    "queue id=${TASK_ID} → ${NEW_STATE:-$FINAL_STATE}" \
    2>/dev/null || true
else
  # フォールバック: webhook 直接送信
  WEBHOOK=""
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    WEBHOOK="$SLACK_WEBHOOK_URL"
  elif [[ -f "${GIT_ROOT}/.env.production" ]]; then
    WEBHOOK=$(grep "^SLACK_WEBHOOK_URL=" "${GIT_ROOT}/.env.production" | head -1 | cut -d= -f2-)
  fi

  if [[ -n "$WEBHOOK" ]]; then
    PAYLOAD=$(printf '{"text":"%s"}' "$SLACK_MSG" | python3 -c "
import sys, json
raw = sys.stdin.read()
# just forward the pre-built JSON
print(raw)
" 2>/dev/null || printf '{"text":"lane-complete-handler: %s"}' "${SLACK_STATUS}")
    curl -sS -X POST "$WEBHOOK" \
      -H "Content-Type: application/json" \
      --data "$PAYLOAD" >/dev/null 2>&1 || true
  fi
fi

exit 0
