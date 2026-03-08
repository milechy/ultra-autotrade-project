#!/usr/bin/env bash
# Claude Code PermissionRequest hook — Slack approval gate
# Claude Code passes the request as JSON on stdin.
# Exit 0 = allow, exit 2 = deny.

set -euo pipefail

# ---------------------------------------------------------------------------
# Load .env.local for SLACK_WEBHOOK_URL (optional)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_LOCAL="${PROJECT_ROOT}/.env.local"

if [[ -f "$ENV_LOCAL" ]]; then
  # shellcheck source=/dev/null
  set -a
  source "$ENV_LOCAL"
  set +a
fi

# ---------------------------------------------------------------------------
# Read JSON from stdin
# ---------------------------------------------------------------------------
INPUT="$(cat)"

# ---------------------------------------------------------------------------
# Parse fields — prefer jq, fall back to python3
# ---------------------------------------------------------------------------
if command -v jq &>/dev/null; then
  SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"')"
  TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // "unknown"')"
  # Summarise tool_input: first 200 chars of the compact JSON
  TOOL_INPUT_SUMMARY="$(printf '%s' "$INPUT" | jq -c '.tool_input // {}' | cut -c1-200)"
else
  SESSION_ID="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','unknown'))")"
  TOOL_NAME="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name','unknown'))")"
  TOOL_INPUT_SUMMARY="$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('tool_input',{}))[:200])")"
fi

PENDING_FILE="/tmp/claude-approval-${SESSION_ID}.pending"

# ---------------------------------------------------------------------------
# Post Slack notification
# ---------------------------------------------------------------------------
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  SLACK_TEXT="$(printf '\u23f8 \u627f\u8a8d\u5f85\u3061: %s %s\nsession_id: %s\n\u627f\u8a8d\u3059\u308b\u5834\u5408: yes %s\n\u62d2\u5426\u3059\u308b\u5834\u5408: no %s' \
    "$TOOL_NAME" "$TOOL_INPUT_SUMMARY" "$SESSION_ID" "$SESSION_ID" "$SESSION_ID")"
  PAYLOAD="$(printf '{"text": "%s"}' "$(printf '%s' "$SLACK_TEXT" | python3 -c "import sys; print(sys.stdin.read().replace('\\\\','\\\\\\\\').replace('\"','\\\\\"').replace(chr(10),'\\\\n'))")")"
  curl -s -X POST \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD" \
    "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
else
  printf 'WARN: SLACK_WEBHOOK_URL not set — skipping Slack notification\n' >&2
fi

# ---------------------------------------------------------------------------
# Create pending file
# ---------------------------------------------------------------------------
printf 'PENDING' > "$PENDING_FILE"

# ---------------------------------------------------------------------------
# Poll for decision (60 seconds, every 2 seconds)
# ---------------------------------------------------------------------------
ELAPSED=0
TIMEOUT=60
INTERVAL=2

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  if [[ -f "$PENDING_FILE" ]]; then
    CONTENT="$(cat "$PENDING_FILE")"
    if [[ "$CONTENT" == "YES" ]]; then
      rm -f "$PENDING_FILE"
      printf 'INFO: Approved by Slack (session_id=%s)\n' "$SESSION_ID" >&2
      exit 0
    elif [[ "$CONTENT" == "NO" ]]; then
      rm -f "$PENDING_FILE"
      printf 'INFO: Denied by Slack (session_id=%s)\n' "$SESSION_ID" >&2
      exit 2
    fi
  fi
  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

# Timeout — deny
rm -f "$PENDING_FILE"
printf 'WARN: Approval timed out after %ds — denying (session_id=%s)\n' "$TIMEOUT" "$SESSION_ID" >&2
exit 2
