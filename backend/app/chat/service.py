# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/chat/service.py
"""チャットサービス。

ユーザーメッセージの保存・Claude 応答生成・履歴取得を提供する。
LLM 呼び出しは既存の app.ai.config パターンを流用し、新規依存を追加しない。
fail-open 設計: API キー未設定 or API 例外時は 500 を返さず固定フォールバック文言を返す。

チャット画面（frontend/app/(liff)/liff-chat/_components/ChatPanel.tsx）は
8個の定型サジェストボタンのみで、自由入力欄は存在しない。ユーザーは AI の回答に対して
自然文で聞き返す・追加情報を渡すことができない。そのため call_claude() には
ユーザー本人の実データ（ポートフォリオ・AI判定・リスク設定）を build_context_block() で
要約して渡し、AI が一回の回答で完結した内容を返せるようにする（system prompt 側でも
「聞き返さない」ことを明示的に指示する）。
"""

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.config import get_ai_settings
from app.ai.models import AIDecision
from app.auth.models import User
from app.chat.models import ChatMessage
from app.chat.schemas import ChatHistoryResponse, ChatMessageOut, ChatResponse
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot

logger = logging.getLogger(__name__)

# fail-open フォールバック文言（API キー未設定 or 例外時）
_FALLBACK_RESPONSE = (
    "申し訳ありません、現在 AI アシスタントが利用できません。しばらくしてから再度お試しください。"
)

# 判定理由の最大文字数（context 肥大化 / token 浪費防止）
_REASON_MAX_LEN = 300

# チャット AI システムプロンプト
#
# UIがボタン選択のみ（自由入力なし）であることを前提に、
# 「聞き返し禁止」「与えられたデータのみで一度に完結した回答」を明示する。
_SYSTEM_PROMPT = (
    "あなたは Ultra AutoTrade のサポートアシスタント「UAT AI」です。"
    "ユーザーが使っているチャット画面には定型の質問ボタンしかなく、自由入力欄はありません。"
    "そのためユーザーはあなたの回答に対して聞き返したり追加情報を伝えたりできません。"
    "この前提を必ず守ってください:"
    "1) ユーザーへ質問を返さない・「詳しく教えてください」「もう少し情報をいただけますか」"
    "のような聞き返しは絶対にしない。"
    "2) メッセージと一緒に渡される「現在の状況」データだけを根拠に、"
    "質問に対する完結した回答を一度で返す。"
    "3) 「現在の状況」に無いデータについては、無いという事実をそのまま伝える"
    "（例:『まだ運用データがありません』）。存在しないデータを推測・創作しない。"
    "4) 投資に関する具体的な売買アドバイス・数値目標は行わず、"
    "サービスの状況説明や一般的な情報提供に留める。"
    "5) 回答は2〜4文程度、分かりやすい日本語で簡潔に書く。"
    "6) 見出し記号(#)、太字(**)、箇条書き記号、区切り線(---)などの"
    "Markdown記法は一切使わない（チャット画面はプレーンテキスト表示のため）。"
)


def _fmt_usd(value: Optional[Decimal]) -> str:
    """USD 金額をフォーマットする。None は「データなし」。"""
    if value is None:
        return "データなし"
    return f"${value:,.2f}"


def _fmt_pct(value: Optional[Decimal]) -> str:
    """パーセンテージをフォーマットする。None は「データなし」。"""
    if value is None:
        return "データなし"
    return f"{value:+.2f}%"


def build_context_block(db: Session, user: User) -> str:
    """チャット AI に渡す「現在の状況」コンテキストを組み立てる。

    ユーザー本人のポートフォリオ・AI判定履歴・リスク設定を要約したテキストを返す。
    データが存在しない項目は「データなし」と明示し、AI が推測で答えないようにする。
    DB クエリ例外は fail-open（空コンテキストを返し、チャット自体は継続する）。

    Args:
        db: SQLAlchemy セッション
        user: 認証済みユーザー

    Returns:
        Claude へのメッセージに埋め込むコンテキスト文字列
    """
    try:
        lines: list[str] = [f"リスクモード: {user.risk_mode or 'データなし'}"]

        snapshot = (
            db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.user_id == user.id)
            .order_by(PortfolioSnapshot.recorded_at.desc())
            .first()
        )
        if snapshot is not None:
            recorded = snapshot.recorded_at.strftime("%Y-%m-%d %H:%M UTC")
            lines.append(
                f"資産評価額: {_fmt_usd(snapshot.total_value_usd)}（記録日時: {recorded}）"
            )
            hf = snapshot.health_factor
            lines.append(
                f"Health Factor: {hf:.2f}" if hf is not None else "Health Factor: データなし"
            )
        else:
            lines.append(
                "ポートフォリオ: データなし（まだ資産スナップショットが記録されていません）"
            )

        monthly = (
            db.query(PortfolioHistory)
            .filter(
                PortfolioHistory.user_id == user.id,
                PortfolioHistory.period_type == "monthly",
            )
            .order_by(PortfolioHistory.period_start.desc())
            .first()
        )
        if monthly is not None:
            lines.append(f"今月の損益: {_fmt_usd(monthly.pnl_usd)}（{_fmt_pct(monthly.pnl_pct)}）")
        else:
            lines.append("今月の損益: データなし（月次集計がまだありません）")

        # 本人宛の判定を優先し、無ければシステム判定（user_id IS NULL）にフォールバックする
        decision = (
            db.query(AIDecision)
            .filter(AIDecision.user_id == user.id)
            .order_by(AIDecision.created_at.desc())
            .first()
        )
        if decision is None:
            decision = (
                db.query(AIDecision)
                .filter(AIDecision.user_id.is_(None))
                .order_by(AIDecision.created_at.desc())
                .first()
            )
        if decision is not None:
            judged_at = decision.created_at.strftime("%Y-%m-%d %H:%M UTC")
            lines.append(
                f"直近のAI判断: {decision.action}（確信度 {decision.confidence}%、判断時刻 {judged_at}）"
            )
            reason = (decision.reason or "").strip()
            if len(reason) > _REASON_MAX_LEN:
                reason = reason[:_REASON_MAX_LEN] + "…"
            lines.append(f"判断理由: {reason or 'データなし'}")
        else:
            lines.append("直近のAI判断: データなし（まだAI判定が実行されていません）")

        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat.service: build_context_block failed for user_id=%s: %s", user.id, exc)
        return "現在の状況データを取得できませんでした。"


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


def call_claude(message: str, context_block: str) -> str:
    """Claude API を呼び出してチャット応答を生成する。

    fail-open 設計:
    - anthropic_api_key が None または空文字列 → フォールバック文言を返す
    - API 呼び出し例外 → フォールバック文言を返す（500 にしない）

    Args:
        message: ユーザーメッセージ（サジェストボタンの定型文言）
        context_block: build_context_block() が組み立てたユーザー実データの要約

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
        user_content = f"[現在の状況]\n{context_block}\n\n[ユーザーの質問]\n{message}"
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
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


def process_chat(db: Session, user: User, message: str) -> ChatResponse:
    """チャットメッセージを処理する。

    処理順序:
    1. ユーザーメッセージを DB に INSERT（role='user'）
    2. ユーザー実データ（ポートフォリオ・AI判定・リスク設定）からコンテキストを組み立て
    3. Claude API で応答を生成（コンテキスト付き）
    4. AI 応答を DB に INSERT（role='ai'）
    5. ChatResponse を返却

    Args:
        db: SQLAlchemy セッション
        user: 認証済みユーザー
        message: ユーザーメッセージ本文

    Returns:
        ChatResponse（response フィールドに AI 応答テキスト）
    """
    # ① ユーザーメッセージを保存
    save_message(db=db, user_id=user.id, role="user", content=message)

    # ② ユーザー実データのコンテキストを組み立て
    context_block = build_context_block(db, user)

    # ③ Claude 呼び出し（fail-open）
    ai_text = call_claude(message, context_block)

    # ④ AI 応答を保存
    save_message(db=db, user_id=user.id, role="ai", content=ai_text)

    # ⑤ レスポンス返却
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
