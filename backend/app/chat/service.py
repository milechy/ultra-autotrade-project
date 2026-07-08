# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/chat/service.py
"""チャットサービス。

ユーザーメッセージの保存・Claude 応答生成・履歴取得を提供する。
LLM 呼び出しは既存の app.ai.config パターンを流用し、新規依存を追加しない。
fail-open 設計: API キー未設定 or API 例外時は 500 を返さず固定フォールバック文言を返す。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.config import get_ai_settings
from app.chat.models import ChatMessage
from app.chat.schemas import ChatHistoryResponse, ChatMessageOut, ChatResponse

logger = logging.getLogger(__name__)

# fail-open フォールバック文言（API キー未設定 or 例外時）
_FALLBACK_RESPONSE = (
    "申し訳ありません、現在 AI アシスタントが利用できません。しばらくしてから再度お試しください。"
)

# チャット AI システムプロンプト
_SYSTEM_PROMPT = (
    "あなたは Ultra AutoTrade のサポートアシスタントです。"
    "ユーザーの質問に対して、分かりやすく丁寧な日本語で回答してください。"
    "投資に関する具体的なアドバイスは行わず、サービスの使い方や一般的な情報提供に留めてください。"
    "回答は必ずプレーンテキストのみで書いてください。"
    "見出し記号(#)、太字(**)、箇条書きの記号、区切り線(---)などのMarkdown記法は"
    "一切使わないでください（チャット画面はMarkdownを表示できないプレーンテキスト表示のため）。"
)


def save_message(db: Session, user_id: int, role: str, content: str) -> ChatMessage:
    """チャットメッセージを DB に保存する。

    Args:
        db: SQLAlchemy セッション
        user_id: ユーザー ID
        role: メッセージ種別（'user' または 'ai'）
        content: メッセージ本文

    Returns:
        保存された ChatMessage インスタンス
    """
    msg = ChatMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def call_claude(message: str) -> str:
    """Claude API を呼び出してチャット応答を生成する。

    fail-open 設計:
    - anthropic_api_key が None または空文字列 → フォールバック文言を返す
    - API 呼び出し例外 → フォールバック文言を返す（500 にしない）

    Args:
        message: ユーザーメッセージ

    Returns:
        Claude の応答テキスト、またはフォールバック文言
    """
    settings = get_ai_settings()

    if not settings.anthropic_api_key:
        logger.warning("chat.service: anthropic_api_key is not set — returning fallback response")
        return _FALLBACK_RESPONSE

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        raw_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                raw_text = block.text
                break
        return raw_text if raw_text else _FALLBACK_RESPONSE
    except Exception as exc:
        logger.warning("chat.service: Claude API call failed: %s", exc)
        return _FALLBACK_RESPONSE


def process_chat(db: Session, user_id: int, message: str) -> ChatResponse:
    """チャットメッセージを処理する。

    処理順序:
    1. ユーザーメッセージを DB に INSERT（role='user'）
    2. Claude API で応答を生成
    3. AI 応答を DB に INSERT（role='ai'）
    4. ChatResponse を返却

    Args:
        db: SQLAlchemy セッション
        user_id: 認証済みユーザー ID
        message: ユーザーメッセージ本文

    Returns:
        ChatResponse（response フィールドに AI 応答テキスト）
    """
    # ① ユーザーメッセージを保存
    save_message(db=db, user_id=user_id, role="user", content=message)

    # ② Claude 呼び出し（fail-open）
    ai_text = call_claude(message)

    # ③ AI 応答を保存
    save_message(db=db, user_id=user_id, role="ai", content=ai_text)

    # ④ レスポンス返却
    return ChatResponse(response=ai_text)


def get_chat_history(
    db: Session,
    user_id: int,
    limit: int = 50,
    before_id: Optional[int] = None,
) -> ChatHistoryResponse:
    """チャット履歴を取得する。

    カーソルページネーション（before_id 方式）を使用する。
    常に user_id で絞り込み、他ユーザーのメッセージは返さない。

    Args:
        db: SQLAlchemy セッション
        user_id: 認証済みユーザー ID
        limit: 取得件数上限（最大 100 件にクランプ）
        before_id: このID より古いメッセージを取得（カーソル）

    Returns:
        ChatHistoryResponse（messages リスト + has_more フラグ）
    """
    clamped_limit = min(limit, 100)
    fetch_limit = clamped_limit + 1  # has_more 判定のため +1 件取得

    query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

    if before_id is not None:
        query = query.filter(ChatMessage.id < before_id)

    rows = (
        query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(fetch_limit)
        .all()
    )

    has_more = len(rows) > clamped_limit
    messages_slice = rows[:clamped_limit]

    return ChatHistoryResponse(
        messages=[ChatMessageOut.model_validate(m) for m in messages_slice],
        has_more=has_more,
    )
