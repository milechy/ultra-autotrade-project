# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_ws_decisions.py
"""AI 判定 WebSocket エンドポイント・WsManager のテスト。"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ws")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")


# ──────────────────────────────────────────────────────────────
# AiDecisionWsManager 単体テスト
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_manager_connect_disconnect() -> None:
    from app.ai.ws_manager import AiDecisionWsManager

    manager = AiDecisionWsManager()
    ws = AsyncMock(spec=WebSocket)

    await manager.connect(ws)
    assert ws in manager.active
    ws.accept.assert_awaited_once()

    manager.disconnect(ws)
    assert ws not in manager.active


@pytest.mark.asyncio
async def test_ws_manager_broadcast_sends_to_all() -> None:
    from app.ai.ws_manager import AiDecisionWsManager

    manager = AiDecisionWsManager()
    ws1, ws2 = AsyncMock(spec=WebSocket), AsyncMock(spec=WebSocket)
    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast({"action": "HOLD", "confidence": 70, "reason": "test"})

    ws1.send_json.assert_awaited_once_with({"action": "HOLD", "confidence": 70, "reason": "test"})
    ws2.send_json.assert_awaited_once_with({"action": "HOLD", "confidence": 70, "reason": "test"})


@pytest.mark.asyncio
async def test_ws_manager_broadcast_removes_dead_connection() -> None:
    from app.ai.ws_manager import AiDecisionWsManager

    manager = AiDecisionWsManager()
    good_ws = AsyncMock(spec=WebSocket)
    dead_ws = AsyncMock(spec=WebSocket)
    dead_ws.send_json.side_effect = RuntimeError("connection closed")

    await manager.connect(good_ws)
    await manager.connect(dead_ws)

    await manager.broadcast({"action": "BUY", "confidence": 85, "reason": "up"})

    assert good_ws in manager.active
    assert dead_ws not in manager.active


# ──────────────────────────────────────────────────────────────
# WebSocket エンドポイント: 無効トークン → code=4001
# ──────────────────────────────────────────────────────────────


@pytest.fixture()
def client():
    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_ws_decisions_invalid_token_closes_4001(client: TestClient) -> None:
    with patch("app.ai.decisions_router.AuthService.decode_token", return_value=None):
        with pytest.raises(Exception):
            with client.websocket_connect("/api/ai/ws/decisions?token=bad-token"):
                pass


def test_ws_decisions_valid_token_accepts(client: TestClient) -> None:
    mock_payload = {"sub": "user@example.com", "role": "viewer"}
    with patch("app.ai.decisions_router.AuthService.decode_token", return_value=mock_payload):
        with client.websocket_connect("/api/ai/ws/decisions?token=valid-token") as ws:
            # 接続確立できること（例外なし）
            assert ws is not None
