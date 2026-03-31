#!/usr/bin/env python3
"""Claude Code CLI → Slack permission request hook.

Sends approval notifications for potentially dangerous operations.
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
        pass


def main() -> None:
    try:
        data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    # Claude Code PreToolUse payload: tool_name + tool_input.command
    tool = data.get("tool_name", data.get("tool", ""))
    command = data.get("tool_input", {}).get("command", data.get("command", ""))

    dangerous_patterns = ["docker", "ssh", "rm -rf", "git push --force", "drop table"]
    if any(pat in command.lower() for pat in dangerous_patterns):
        send_slack(
            f"⚠️ Claude Code 承認リクエスト:\nツール: {tool}\nコマンド: `{command}`"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
