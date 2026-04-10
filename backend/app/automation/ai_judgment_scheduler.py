# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/automation/ai_judgment_scheduler.py
"""AI判定定期スケジューラー。

4時間ごとに AI 判定を実行し、結果を ai_decisions に保存する。
BUY/SELL 判定時はアクティブユーザー全員に Proposal を作成する。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AIDecision
from app.ai.schemas import CrossValidationResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.auth.models import User
from app.data_feeds.context import build_market_context
from app.database import SessionLocal
from app.knowledge.schemas import KnowledgeSearchRequest
from app.knowledge.service import KnowledgeService
from app.proposals.models import Proposal

logger = logging.getLogger(__name__)

# --- スケジューラー実行状態（/health から参照） ---
_scheduler_started: bool = False
_last_run_at: "datetime | None" = None
_next_run_at: "datetime | None" = None
_last_error_msg: "str | None" = None


def get_scheduler_status() -> "dict[str, Any]":
    """スケジューラーの稼働状態を返す（/health エンドポイント用）。"""
    return {
        "running": _scheduler_started,
        "last_run": _last_run_at.isoformat() if _last_run_at else None,
        "next_run": _next_run_at.isoformat() if _next_run_at else None,
        "last_error": _last_error_msg,
    }


_DEFAULT_QUERY = "DeFi market analysis"
_PROPOSAL_ASSET = "USDC"
_PROPOSAL_AMOUNT = Decimal("1000")
_PROPOSAL_AMOUNT_USD = Decimal("1000.00")
_PROPOSAL_EXPIRES_HOURS = 24


def save_ai_decision(
    db: Session,
    result: CrossValidationResult,
    query: str,
    user_id: Optional[int] = None,
) -> AIDecision:
    """CrossValidationResult を ai_decisions テーブルに保存して返す。

    Args:
        db: SQLAlchemy セッション。
        result: AI クロスバリデーション結果。
        query: 判定に使ったクエリ文字列。
        user_id: 紐づけるユーザー ID（None = システム判定）。

    Returns:
        保存済みの AIDecision インスタンス。
    """
    decision = AIDecision(
        user_id=user_id,
        query=query,
        action=result.final_action.value,
        confidence=result.final_confidence,
        reason=result.final_reason,
        primary_provider=result.primary.provider.value,
        primary_action=result.primary.action.value,
        primary_confidence=result.primary.confidence,
        secondary_provider=result.secondary.provider.value if result.secondary else None,
        secondary_action=result.secondary.action.value if result.secondary else None,
        secondary_confidence=result.secondary.confidence if result.secondary else None,
        agreed=result.agreed,
        rag_context_json=None,
    )
    db.add(decision)
    db.flush()  # id を確定させる
    return decision


def _create_proposals_for_users(
    db: Session,
    decision: AIDecision,
    result: CrossValidationResult,
) -> int:
    """アクティブユーザー全員に Proposal を作成し、作成件数を返す。

    Args:
        db: SQLAlchemy セッション。
        decision: 保存済みの AIDecision。
        result: AI クロスバリデーション結果。

    Returns:
        作成した Proposal の件数。
    """
    operation = "SUPPLY" if result.final_action == TradeAction.BUY else "WITHDRAW"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_PROPOSAL_EXPIRES_HOURS)
    reason = result.final_reason or "AI判定による提案"

    active_users = db.scalars(
        select(User).where(
            User.is_active == True,  # noqa: E712
            User.execution_policy == "require_approval",
        )
    ).all()

    count = 0
    for user in active_users:
        proposal = Proposal(
            user_id=user.id,
            ai_decision_id=decision.id,
            operation=operation,
            asset=_PROPOSAL_ASSET,
            amount=_PROPOSAL_AMOUNT,
            amount_usd=_PROPOSAL_AMOUNT_USD,
            reason=reason,
            expires_at=expires_at,
        )
        db.add(proposal)
        count += 1

    return count


def run_ai_judgment_job(db: Optional[Session] = None) -> dict[str, Any]:
    """AI 判定を実行して DB に保存する同期関数。

    BUY / SELL 判定時はアクティブユーザー全員に Proposal を作成する。

    Args:
        db: 外部から渡すセッション（テスト用）。None の場合は SessionLocal を使用。

    Returns:
        dict: {"action": str, "confidence": int, "proposals_created": int, "decision_id": int}
    """
    _own_session = db is None
    if _own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    try:
        # RAG コンテキスト取得（失敗時は空のコンテキストでフォールバック）
        rag_ctx: RAGContext
        try:
            svc = KnowledgeService()
            search_request = KnowledgeSearchRequest(query=_DEFAULT_QUERY, top_k=5)
            search_results = svc.search(db, search_request)
            rag_ctx = RAGContext(
                chunks=[r.content for r in search_results],
                query=_DEFAULT_QUERY,
                source_count=len(search_results),
            )
        except Exception as exc:
            logger.warning("RAG context retrieval failed, using empty context: %s", exc)
            rag_ctx = RAGContext(chunks=[], query=_DEFAULT_QUERY, source_count=0)

        # Market context（ニュース・地政学リスク・マクロ）をキャッシュから取得
        context_degraded = False
        market_ctx: Any
        try:
            market_ctx = build_market_context()
        except Exception as exc:
            context_degraded = True
            logger.warning("build_market_context() failed, using degraded context: %s", exc)
            market_ctx = {
                "degraded": True,
                "reason": str(exc),
                "geopolitical_events": [],
                "market_data": {},
            }

        if context_degraded:
            logger.warning("AI judgment proceeding with degraded market context")

        # AI 判定実行
        result: CrossValidationResult = AIService().judge_with_rag(
            query=_DEFAULT_QUERY,
            rag_context=rag_ctx,
            market_context=market_ctx,
        )

        # DB 保存
        decision = save_ai_decision(db, result, _DEFAULT_QUERY)

        # BUY / SELL 時は Proposal 作成
        proposals_created = 0
        if result.final_action in (TradeAction.BUY, TradeAction.SELL):
            proposals_created = _create_proposals_for_users(db, decision, result)

        db.commit()

        return {
            "action": result.final_action.value,
            "confidence": result.final_confidence,
            "proposals_created": proposals_created,
            "decision_id": decision.id,
        }

    except Exception as exc:
        logger.error("AI judgment job failed: %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: S110
            pass
        raise
    finally:
        if _own_session:
            db.close()


async def ai_judgment_loop(
    interval_hours: int = 4,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """interval_hours ごとに run_ai_judgment_job() を実行するループ。

    Args:
        interval_hours: 実行間隔（時間）。デフォルト 4 時間。
        on_error: 失敗時に呼び出す同期コールバック（Slack 通知等）。
    """
    global _scheduler_started, _last_run_at, _next_run_at, _last_error_msg
    _scheduler_started = True
    await asyncio.sleep(0)  # イベントループに制御を返す
    while True:
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, run_ai_judgment_job)
            _last_run_at = datetime.now(timezone.utc)
            _last_error_msg = None
            logger.info("AI judgment completed: %s", result)

            # AI判定直後にポートフォリオスナップショットを記録（fail-open）
            try:
                from app.portfolio.snapshot_service import record_portfolio_snapshot  # noqa: PLC0415,I001

                snap_result = await loop.run_in_executor(None, record_portfolio_snapshot)
                logger.info("Portfolio snapshot recorded: %s", snap_result)
            except Exception as snap_exc:
                logger.warning("Portfolio snapshot skipped (non-critical): %s", snap_exc)
        except Exception as exc:
            _last_error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("AI judgment job failed: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as cb_exc:
                    logger.error("on_error callback failed: %s", cb_exc)
        _next_run_at = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
        await asyncio.sleep(interval_hours * 3600)
