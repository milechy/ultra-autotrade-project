# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/ws_manager.py
"""WebSocket 接続管理: AI 判定をリアルタイム配信する。"""

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AiDecisionWsManager:
    """接続済み WebSocket クライアントを管理し、AI 判定結果をブロードキャストする。"""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self.active.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, data: dict[str, Any]) -> None:
        """全接続クライアントに送信。dead connection は自動削除。"""
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = AiDecisionWsManager()
