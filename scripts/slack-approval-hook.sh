#!/usr/bin/env bash
# Claude Code PermissionRequest hook — Slack Block Kit approval gate
# Exit 0 = allow, exit 2 = deny.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load env files for SLACK_WEBHOOK_URL
for env_file in "${PROJECT_ROOT}/.env.local" "${PROJECT_ROOT}/.env.staging"; do
  if [[ -f "$env_file" ]]; then
    set -a; source "$env_file"; set +a
    break
  fi
done

API_BASE="${HOOKS_API_BASE:-https://api.ultra-auto-trade.com}"

# ---------------------------------------------------------------------------
# Read JSON from stdin
# ---------------------------------------------------------------------------
INPUT="$(cat)"

if command -v jq &>/dev/null; then
  SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"')"
  TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // "unknown"')"
  TOOL_INPUT_SUMMARY="$(printf '%s' "$INPUT" | jq -c '.tool_input // {}' | cut -c1-300)"
else
  SESSION_ID="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','unknown'))")"
  TOOL_NAME="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name','unknown'))")"
  TOOL_INPUT_SUMMARY="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('tool_input',{}))[:300])")"
fi

# ---------------------------------------------------------------------------
# Send Block Kit message with Approve / Deny buttons
# ---------------------------------------------------------------------------
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  SLACK_WEBHOOK_URL="$SLACK_WEBHOOK_URL" SESSION_ID="$SESSION_ID" \
  TOOL_NAME="$TOOL_NAME" TOOL_INPUT_SUMMARY="$TOOL_INPUT_SUMMARY" \
  python3 - <<'PYEOF'
import json, os, sys, urllib.request

webhook = os.environ["SLACK_WEBHOOK_URL"]
sid     = os.environ["SESSION_ID"]
tool    = os.environ["TOOL_NAME"]
tinput  = os.environ["TOOL_INPUT_SUMMARY"][:200]

blocks = [
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*⏸ Claude Code 承認リクエスト*\n"
                f"*ツール:* `{tool}`\n"
                f"*内容:* `{tinput}`\n"
                f"*session:* `{sid}`"
            ),
        },
    },
    {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ 承認", "emoji": True},
                "style": "primary",
                "action_id": f"approve_{sid}",
                "value": sid,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "❌ 拒否", "emoji": True},
                "style": "danger",
                "action_id": f"deny_{sid}",
                "value": sid,
            },
        ],
    },
]

payload = json.dumps({"blocks": blocks}).encode()
req = urllib.request.Request(
    webhook, data=payload,
    headers={"Content-Type": "application/json"}, method="POST",
)
try:
    urllib.request.urlopen(req, timeout=5)
except Exception as e:
    print(f"WARN: Slack send failed: {e}", file=sys.stderr)
PYEOF
else
  printf 'WARN: SLACK_WEBHOOK_URL not set\n' >&2
fi

# ---------------------------------------------------------------------------
# Poll staging API for decision (60 seconds, every 3 seconds)
# ---------------------------------------------------------------------------
ELAPSED=0
TIMEOUT=60
INTERVAL=3

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  RESULT="$(curl -sf "${API_BASE}/api/hooks/approval/${SESSION_ID}" 2>/dev/null || echo '{"status":"PENDING"}')"
  STATUS="$(printf '%s' "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','PENDING'))" 2>/dev/null || echo 'PENDING')"

  if [[ "$STATUS" == "YES" ]]; then
    printf 'INFO: Approved (session_id=%s)\n' "$SESSION_ID" >&2
    exit 0
  elif [[ "$STATUS" == "NO" ]]; then
    printf 'INFO: Denied (session_id=%s)\n' "$SESSION_ID" >&2
    exit 2
  fi

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

printf 'WARN: Approval timed out after %ds — denying\n' "$TIMEOUT" >&2
exit 2
