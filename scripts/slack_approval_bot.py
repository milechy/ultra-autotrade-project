"""Slack bot daemon that writes YES/NO approval decisions for Claude Code hooks.

Usage:
    python3 scripts/slack_approval_bot.py

Environment variables:
    SLACK_BOT_TOKEN       xoxb-... token with channels:history scope
    SLACK_APPROVAL_CHANNEL  channel name (e.g. #claude-approvals) or channel ID
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 3.0  # seconds between Slack API polls
TMP_DIR: Path = Path("/tmp")  # noqa: S108
PENDING_PREFIX: str = "claude-approval-"
PENDING_SUFFIX: str = ".pending"


def _load_env_local() -> None:
    """Load .env.local from the project root if it exists."""
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env.local"
    if not env_path.exists():
        return
    with env_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _resolve_channel_id(token: str, channel_name: str) -> str:
    """Resolve a channel name (with or without #) to a channel ID."""
    name = channel_name.lstrip("#")
    url = "https://slack.com/api/conversations.list"
    headers = {"Authorization": f"Bearer {token}"}
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 200, "exclude_archived": "true"}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"conversations.list error: {data.get('error')}")
        for ch in data.get("channels", []):
            if ch.get("name") == name:
                return str(ch["id"])
        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    # If not found, assume the caller already passed a channel ID
    return channel_name


def _fetch_new_messages(
    token: str,
    channel_id: str,
    oldest: str,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch messages newer than *oldest* timestamp.

    Returns (messages, latest_ts) where latest_ts is the newest ts seen.
    """
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {
        "channel": channel_id,
        "oldest": oldest,
        "limit": 50,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        error = data.get("error", "unknown")
        if error == "not_in_channel":
            raise RuntimeError(
                "Bot is not in the approval channel. Invite it with /invite @<bot-name>."
            )
        raise RuntimeError(f"conversations.history error: {error}")

    messages: list[dict[str, Any]] = data.get("messages", [])
    # Messages come newest-first; reverse so we process oldest first
    messages = list(reversed(messages))

    latest_ts = oldest
    for msg in messages:
        ts = msg.get("ts", "0")
        if ts > latest_ts:
            latest_ts = ts
    return messages, latest_ts


def _find_oldest_pending_file() -> Path | None:
    """Return the path to the oldest .pending file, or None if none exist."""
    files = list(TMP_DIR.glob(f"{PENDING_PREFIX}*{PENDING_SUFFIX}"))
    if not files:
        return None
    # Sort by mtime ascending → oldest first
    files.sort(key=lambda p: p.stat().st_mtime)
    return files[0]


def _session_id_from_path(path: Path) -> str:
    """Extract session_id from /tmp/claude-approval-{session_id}.pending."""
    name = path.name
    without_prefix = name.removeprefix(PENDING_PREFIX)
    return without_prefix.removesuffix(PENDING_SUFFIX)


def _pending_path(session_id: str) -> Path:
    """Return the Path for a given session_id's pending file."""
    return TMP_DIR / f"{PENDING_PREFIX}{session_id}{PENDING_SUFFIX}"  # noqa: S108


def _write_decision(session_id: str, decision: str) -> bool:
    """Write YES or NO to the pending file. Returns True if file existed."""
    pending_file = _pending_path(session_id)
    if not pending_file.exists():
        logger.warning("Pending file not found: %s", pending_file)
        return False
    pending_file.write_text(decision)
    logger.info("Wrote %s to %s", decision, pending_file)
    return True


def _process_message(text: str) -> None:
    """Parse a Slack message text and write approval decision if applicable."""
    text = text.strip().lower()
    parts = text.split()
    if not parts:
        return

    verdict_word = parts[0]
    if verdict_word not in ("yes", "no"):
        return

    decision = "YES" if verdict_word == "yes" else "NO"

    if len(parts) >= 2:
        # "yes <session_id>" or "no <session_id>"
        session_id = parts[1]
        pending_file = _pending_path(session_id)
        if pending_file.exists():
            _write_decision(session_id, decision)
        else:
            logger.warning(
                "Received '%s %s' but no pending file found for that session.",
                verdict_word,
                session_id,
            )
    else:
        # Bare "yes" or "no" — apply to oldest pending file
        oldest = _find_oldest_pending_file()
        if oldest is None:
            logger.warning("Received bare '%s' but no pending files found.", verdict_word)
            return
        session_id = _session_id_from_path(oldest)
        _write_decision(session_id, decision)


def run_bot(token: str, channel_id: str) -> None:
    """Main polling loop."""
    # Start polling from now (ignore historical messages)
    oldest_ts: str = str(time.time())
    logger.info("Slack approval bot started. Polling channel %s", channel_id)

    while True:
        try:
            messages, new_oldest = _fetch_new_messages(token, channel_id, oldest_ts)
            for msg in messages:
                msg_text: str = msg.get("text", "")
                # Skip bot messages to avoid feedback loops
                if msg.get("bot_id") or msg.get("subtype"):
                    continue
                if msg_text:
                    _process_message(msg_text)
            # Advance timestamp only when we actually got messages
            if new_oldest > oldest_ts:
                oldest_ts = new_oldest
        except requests.RequestException as exc:
            logger.error("Network error polling Slack: %s", exc)
        except RuntimeError as exc:
            logger.error("Slack API error: %s", exc)
            # Fatal misconfiguration errors
            if "not_in_channel" in str(exc):
                sys.exit(1)

        time.sleep(POLL_INTERVAL)


def main() -> None:
    _load_env_local()

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_name = os.environ.get("SLACK_APPROVAL_CHANNEL", "")

    if not token:
        logger.error("SLACK_BOT_TOKEN environment variable is not set.")
        sys.exit(1)
    if not channel_name:
        logger.error("SLACK_APPROVAL_CHANNEL environment variable is not set.")
        sys.exit(1)

    logger.info("Resolving channel: %s", channel_name)
    channel_id = _resolve_channel_id(token, channel_name)
    logger.info("Resolved channel ID: %s", channel_id)

    run_bot(token, channel_id)


if __name__ == "__main__":
    main()
