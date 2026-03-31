#!/usr/bin/env python3
"""Claude Code CLI → Slack notification hook.

Sends a notification to Slack when Claude Code completes a task.
Reads SLACK_WEBHOOK_URL from environment or .env.staging.
"""
import json
import os
import sys
import urllib.request
import urllib.error


def get_webhook_url() -> str | None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if url:
        return url
    # Fallback: read from .env.staging
    env_file = os.path.join(os.path.dirname(__file__), "../../.env.staging")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("SLACK_WEBHOOK_URL="):
                    return line.strip().split("=", 1)[1]
    return None


def send_slack(message: str) -> None:
    url = get_webhook_url()
    if not url:
        return
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, TimeoutError):
        pass  # Slack failure should never block CLI


def main() -> None:
    try:
        data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    # Claude Code passes event type via env var; Stop hook sends no stdin JSON
    hook_type = os.environ.get("HOOK_EVENT_TYPE", data.get("type", data.get("event", "")))
    summary = data.get("summary", "タスク完了")

    # Stop hook: always notify (it's called only on session end)
    # PostToolUse: notify only when summary is present
    if hook_type == "Stop" or (hook_type == "PostToolUse" and summary != "タスク完了"):
        send_slack(f"🤖 Claude Code: {summary}")

    sys.exit(0)


if __name__ == "__main__":
    main()
