# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/chat/schemas.py
"""チャット API の Pydantic スキーマ定義。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """POST /api/chat リクエストボディ。"""

    # 空メッセージの INSERT / 無制限 TEXT によるトークン浪費を防ぐためバリデーション
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    """チャットメッセージの出力スキーマ（履歴表示用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """GET /api/chat/history レスポンス。"""

    messages: list[ChatMessageOut]
    has_more: bool


class ChatResponse(BaseModel):
    """POST /api/chat レスポンス。

    フロントエンド ChatPanel は data.response ?? data.message ?? data.content の
    順でキーを参照するため、response キーを推奨フィールドとして定義する。
    """

    response: str
