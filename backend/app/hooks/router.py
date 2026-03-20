# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Slack interactive approval endpoints for Claude Code CLI hooks.

POST /api/hooks/slack-interaction  — Slack sends button-click payloads here
GET  /api/hooks/approval/{session_id} — local hook polls for decision
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hooks", tags=["hooks"])

# In-memory store: session_id → "YES" | "NO" | "PENDING"
# Entries expire after 10 minutes.
_decisions: dict[str, tuple[str, float]] = {}
_TTL = 600  # seconds


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _decisions.items() if now - ts > _TTL]
    for k in expired:
        del _decisions[k]


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return True  # skip verification in dev
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return True
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/slack-interaction")
async def slack_interaction(request: Request) -> Response:
    """Receive Slack button-click interaction payload."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    # Slack sends payload as URL-encoded form: payload=<json>
    try:
        form = await request.form()
        raw = form.get("payload", "")
        data: dict[str, Any] = json.loads(str(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    actions = data.get("actions", [])
    if not actions:
        return Response(content="ok")

    action = actions[0]
    action_id: str = action.get("action_id", "")

    # PR review actions (review_*) → forward to Flask app on port 5000
    if action_id.startswith("review_"):
        flask_url = os.getenv("SLACK_FLASK_URL", "http://localhost:5000/slack/interactions")
        try:
            headers: dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
            if timestamp:
                headers["X-Slack-Request-Timestamp"] = timestamp
            if signature:
                headers["X-Slack-Signature"] = signature
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    flask_url,
                    data={"payload": json.dumps(data)},
                    headers=headers,
                    timeout=10.0,
                )
            return Response(content=resp.content, media_type="application/json")
        except Exception as e:
            logger.warning("Flask forward failed: %s", e)
            return Response(
                content='{"text":"PR action forwarding failed"}', media_type="application/json"
            )

    # Claude Code approval: "approve_{session_id}" or "deny_{session_id}"
    if action_id.startswith("approve_"):
        session_id = action_id[len("approve_") :]
        decision = "YES"
    elif action_id.startswith("deny_"):
        session_id = action_id[len("deny_") :]
        decision = "NO"
    else:
        logger.warning("Unknown action_id: %s", action_id)
        return Response(content="ok")

    if not session_id:
        logger.warning("Empty session_id for action_id: %s", action_id)
        return Response(content="ok")

    _purge_expired()
    _decisions[session_id] = (decision, time.time())
    logger.info("Slack approval: session=%s decision=%s", session_id, decision)

    # Update the Slack message to reflect the decision
    response_url: str = data.get("response_url", "")
    if response_url and response_url.startswith("https://"):
        label = "✅ 承認しました" if decision == "YES" else "❌ 拒否しました"
        user = data.get("user", {}).get("name", "?")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    response_url,
                    json={"replace_original": True, "text": f"{label} (by @{user})"},
                    timeout=5.0,
                )
        except Exception as exc:
            logger.warning("Failed to update Slack message via response_url: %s", exc)

    return Response(content="")


@router.get("/approval/{session_id}")
async def get_approval(session_id: str) -> dict[str, str]:
    """Local hook polls this to get the approval decision."""
    _purge_expired()
    if session_id not in _decisions:
        return {"status": "PENDING"}
    decision, _ = _decisions[session_id]
    return {"status": decision}
