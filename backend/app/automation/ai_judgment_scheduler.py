# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/automation/ai_judgment_scheduler.py
"""AI判定定期スケジューラー。

ティア別間隔で AI 判定を実行し、結果を ai_decisions に保存する。
- UPPER ティア:  AI_JUDGMENT_INTERVAL_HOURS_UPPER (デフォルト 4 時間)
- MIDDLE ティア: AI_JUDGMENT_INTERVAL_HOURS_MIDDLE (デフォルト 6 時間)
- LOWER ティア:  AI_JUDGMENT_INTERVAL_HOURS_LOWER (デフォルト 8 時間)
- GENERAL ティア: AI_JUDGMENT_INTERVAL_HOURS_GENERAL (デフォルト 8 時間、v9 互換)
BUY/SELL 判定時はティア間隔を満たすアクティブユーザーに Proposal を作成する。
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.judgment_log import get_judgment_logger
from app.ai.models import AIDecision
from app.ai.schemas import CrossValidationResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.auth.constants import ExecutionPolicy
from app.auth.models import InvestmentTier, User, normalize_tier
from app.automation.aave_data_fetcher import fetch_aave_market_data_safe
from app.data_feeds.context import build_market_context
from app.database import SessionLocal
from app.knowledge.schemas import KnowledgeSearchRequest
from app.knowledge.service import KnowledgeService
from app.proposals.models import Proposal

# ティア別デフォルト判定間隔（時間）
_DEFAULT_INTERVAL_UPPER = 4
_DEFAULT_INTERVAL_MIDDLE = 6
_DEFAULT_INTERVAL_LOWER = 8
_DEFAULT_INTERVAL_GENERAL = 8  # v9 互換 (LOWER と同値)

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


def _get_tier_interval_hours(tier: str) -> int:
    """ティアに応じた AI 判定間隔（時間）を返す。

    環境変数で上書き可能:
    - AI_JUDGMENT_INTERVAL_HOURS_UPPER (デフォルト 4)
    - AI_JUDGMENT_INTERVAL_HOURS_MIDDLE (デフォルト 6)
    - AI_JUDGMENT_INTERVAL_HOURS_LOWER (デフォルト 8)
    - AI_JUDGMENT_INTERVAL_HOURS_GENERAL (デフォルト 8、v9 互換)
    """
    if tier == InvestmentTier.UPPER.value:
        return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_UPPER", str(_DEFAULT_INTERVAL_UPPER)))
    if tier == InvestmentTier.MIDDLE.value:
        return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_MIDDLE", str(_DEFAULT_INTERVAL_MIDDLE)))
    if tier == InvestmentTier.LOWER.value:
        return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_LOWER", str(_DEFAULT_INTERVAL_LOWER)))
    # GENERAL (v9 互換) または未知の値 → GENERAL のデフォルト (= LOWER と同値)
    return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_GENERAL", str(_DEFAULT_INTERVAL_GENERAL)))


def _is_user_due_for_judgment(user: User, now: datetime) -> bool:
    """ユーザーがティア別間隔を満たしているか判定する。

    last_judgment_at が None（初回）または interval 経過済みの場合 True を返す。
    """
    if user.last_judgment_at is None:
        return True
    interval = _get_tier_interval_hours(user.tier)
    last = user.last_judgment_at
    # timezone-aware 比較
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now >= last + timedelta(hours=interval)


def _create_proposals_for_users(
    db: Session,
    decision: AIDecision,
    result: CrossValidationResult,
) -> int:
    """ティア別間隔を満たすアクティブユーザーに Proposal を作成し、作成件数を返す。

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
    now = datetime.now(timezone.utc)

    active_users = db.scalars(
        select(User).where(
            User.is_active == True,  # noqa: E712
            User.execution_policy == ExecutionPolicy.REQUIRE_APPROVAL.value,
        )
    ).all()

    import os  # noqa: PLC0415

    from app.billing.dynamic_fee import calculate_fee_by_market  # noqa: PLC0415

    fixed_cost = Decimal(os.getenv("TRADE_FIXED_COST_USD", "0.27"))

    count = 0
    for user in active_users:
        if not _is_user_due_for_judgment(user, now):
            logger.debug(
                "Skipping proposal for user %d (tier=%s, last_judgment_at=%s)",
                user.id,
                user.tier,
                user.last_judgment_at,
            )
            continue

        # 動的手数料計算: デフォルトAPY 4%（安定期）を使用
        # 30日保有での予想利益 = amount × (APY/100) × (30/365)
        _default_apy = Decimal("4")
        _expected_profit = (
            _PROPOSAL_AMOUNT_USD * _default_apy / Decimal("100") * Decimal("30") / Decimal("365")
        )
        market_fee = calculate_fee_by_market(
            trade_amount_usd=_PROPOSAL_AMOUNT_USD,
            tier=normalize_tier(user.tier, user_id=user.id).value,
            current_apy=_default_apy,
            expected_profit_usd=_expected_profit,
            fixed_cost_usd=fixed_cost,
        )

        if not market_fee.should_trade:
            logger.info(
                "DynamicFee: should_trade=False for user %d — skipping proposal (%s)",
                user.id,
                market_fee.reason,
            )
            continue

        proposal = Proposal(
            user_id=user.id,
            ai_decision_id=decision.id,
            operation=operation,
            asset=_PROPOSAL_ASSET,
            amount=_PROPOSAL_AMOUNT,
            amount_usd=_PROPOSAL_AMOUNT_USD,
            reason=reason,
            expires_at=expires_at,
            fee_rate=market_fee.fee_rate,
            fee_amount=market_fee.fee_amount,
        )
        db.add(proposal)
        user.last_judgment_at = now
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

        # Market context（ニュース・地政学リスク・マクロ + Aave + cognitive_state）
        # を組み立てる。Aave 取得は fail-open ヘルパーで、個別失敗は None フォールバック。
        # cognitive_state は HOLD 連続抑制のため LLM プロンプトに渡す。
        context_degraded = False
        market_ctx: Any
        try:
            aave_data = fetch_aave_market_data_safe()
            cognitive_state = get_judgment_logger().get_cognitive_state()
            market_ctx = build_market_context(
                aave_utilization_rate=aave_data["utilization_rate"],
                aave_supply_apy=aave_data["supply_apy"],
                aave_borrow_apy=aave_data["borrow_apy"],
                health_factor=aave_data["health_factor"],
                cognitive_state=cognitive_state,
            )
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
    interval_hours: int = _DEFAULT_INTERVAL_UPPER,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """UPPER ティア間隔（最小値）で tick し、ユーザーごとにティア別間隔を適用するループ。

    tick 間隔は AI_JUDGMENT_INTERVAL_HOURS_UPPER（デフォルト 4 時間）に合わせる。
    各 tick で _create_proposals_for_users がユーザーごとのティア間隔を確認し、
    GENERAL ティアのユーザーは 8 時間未満の場合はスキップされる。

    Args:
        interval_hours: tick 間隔（時間）。デフォルトは UPPER ティア間隔。
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
