# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/chat/router.py
"""チャット API ルーター。

エンドポイント:
    POST /chat   → /api/chat   (main.py: prefix="/api")
    GET  /chat/history → /api/chat/history
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db

from .schemas import ChatHistoryResponse, ChatRequest, ChatResponse
from .service import get_chat_history, process_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def post_chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """ユーザーメッセージを送信し、AI 応答を返す。

    処理内容:
    1. ユーザーメッセージを chat_messages に保存
    2. Claude API を呼び出して応答を生成
    3. AI 応答を chat_messages に保存
    4. ChatResponse を返却

    Args:
        body: リクエストボディ（message フィールド）
        user: 認証済みユーザー
        db: DB セッション

    Returns:
        ChatResponse（response フィールドに AI 応答テキスト）
    """
    return process_chat(db=db, user=user, message=body.message)


@router.get("/history", response_model=ChatHistoryResponse)
def get_history(
    limit: int = 50,
    before_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatHistoryResponse:
    """チャット履歴を取得する。

    カーソルページネーション（before_id 方式）:
    - before_id 未指定: 最新 limit 件を返す
    - before_id 指定: そのID より古いメッセージを返す
    - has_more=True の場合、返却リストの末尾 id を次の before_id として使う

    Args:
        limit: 取得件数（デフォルト 50、最大 100 にクランプ）
        before_id: カーソル位置（このID より古いメッセージを取得）
        user: 認証済みユーザー
        db: DB セッション

    Returns:
        ChatHistoryResponse（messages リスト + has_more フラグ）
    """
    return get_chat_history(db=db, user_id=user.id, limit=limit, before_id=before_id)
