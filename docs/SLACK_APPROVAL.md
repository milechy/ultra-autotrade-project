# Slack Approval for Claude Code

## Overview

This system adds a human-in-the-loop approval gate to Claude Code's `PermissionRequest` hook.

When Claude Code wants to execute a tool that is not in the pre-approved allow list, it calls
`scripts/slack-approval-hook.sh`. The hook:

1. Posts a notification to Slack: which tool was requested and its input summary.
2. Waits up to 60 seconds for a human to reply "yes" or "no" in the approval channel.
3. Returns exit 0 (allow) for "yes", or exit 2 (deny) for "no" or timeout.

A companion daemon (`scripts/slack_approval_bot.py`) monitors the Slack channel for replies
and writes the decision to a temporary file that the hook reads.

---

## Prerequisites

| Variable | Description |
|---|---|
| `SLACK_WEBHOOK_URL` | Incoming Webhook URL for posting notifications |
| `SLACK_BOT_TOKEN` | Bot token (`xoxb-...`) with `channels:history` and `channels:read` scopes |
| `SLACK_APPROVAL_CHANNEL` | Channel name (e.g. `#claude-approvals`) or channel ID |

---

## Setup

### 1. Create a Slack App

1. Go to https://api.slack.com/apps and create a new app (From Scratch).
2. Under **Incoming Webhooks**, activate webhooks and add a webhook to your approval channel.
   Copy the webhook URL → this is `SLACK_WEBHOOK_URL`.
3. Under **OAuth & Permissions**, add the following Bot Token Scopes:
   - `channels:history` — read messages in public channels
   - `channels:read` — list channels (for name-to-ID resolution)
   - `groups:history` / `groups:read` — if using a private channel
4. Install the app to your workspace. Copy the **Bot User OAuth Token** (`xoxb-...`)
   → this is `SLACK_BOT_TOKEN`.

### 2. Invite the Bot to the Channel

In Slack, open the approval channel and run:

```
/invite @<your-bot-name>
```

### 3. Set Environment Variables

Add the following to `.env.local` in the project root (this file is git-ignored):

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_BOT_TOKEN=xoxb-...
SLACK_APPROVAL_CHANNEL=#claude-approvals
```

### 4. Make the Hook Executable

```bash
chmod +x scripts/slack-approval-hook.sh
```

This is already done during initial setup.

---

## Usage

### Start the Approval Bot Daemon

The bot must be running before Claude Code sessions that require approval.

```bash
# Foreground (for testing)
python3 scripts/slack_approval_bot.py

# Background (recommended for persistent use)
nohup python3 scripts/slack_approval_bot.py > /tmp/slack-approval-bot.log 2>&1 &
echo $! > /tmp/slack-approval-bot.pid
```

To stop the daemon:

```bash
kill "$(cat /tmp/slack-approval-bot.pid)"
```

### Approving / Denying Requests

When Claude Code triggers a permission request, a message appears in the approval channel:

```
⏸ 承認待ち: Bash {"command": "rm -rf /tmp/test"}
session_id: abc123
承認する場合: yes abc123
拒否する場合: no abc123
```

Reply in the channel:

| Reply | Effect |
|---|---|
| `yes abc123` | Allow the operation for session `abc123` |
| `no abc123` | Deny the operation for session `abc123` |
| `yes` | Allow the operation for the oldest pending session |
| `no` | Deny the operation for the oldest pending session |

The hook will unblock within ~2 seconds of receiving the reply.

---

## Timeout Behavior

If no reply is received within **60 seconds**, the hook automatically denies the request
(exit 2). Claude Code treats this as a denied permission.

---

## How It Works (Technical)

```
Claude Code
  → PermissionRequest hook
    → slack-approval-hook.sh
        → POST notification to SLACK_WEBHOOK_URL
        → create /tmp/claude-approval-{session_id}.pending (contains "PENDING")
        → poll loop (every 2s, up to 60s)
            ← reads file contents
            ← "YES" → exit 0 (allow)
            ← "NO"  → exit 2 (deny)
            ← timeout → exit 2 (deny)

Slack (human types "yes abc123")
  → slack_approval_bot.py (polling every 3s)
      → writes "YES" to /tmp/claude-approval-{session_id}.pending
```

---

## Testing

### Test the Hook Manually

```bash
# Simulate a PermissionRequest for Bash
echo '{"session_id":"test001","tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' \
  | bash scripts/slack-approval-hook.sh
echo "Exit code: $?"
```

Then, in another terminal, simulate an approval:

```bash
# Approve
echo -n "YES" > /tmp/claude-approval-test001.pending

# Or deny
echo -n "NO" > /tmp/claude-approval-test001.pending
```

### Test the Bot

```bash
# Run the bot (requires SLACK_BOT_TOKEN and SLACK_APPROVAL_CHANNEL)
source .env.local
python3 scripts/slack_approval_bot.py
```

Then post "yes test001" in the approval Slack channel. The bot should write "YES" to
`/tmp/claude-approval-test001.pending` within ~3 seconds.

### Verify ruff Compliance

```bash
ruff check scripts/slack_approval_bot.py
ruff format --check scripts/slack_approval_bot.py
```
