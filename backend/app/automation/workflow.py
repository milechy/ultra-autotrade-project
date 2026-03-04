# backend/app/automation/workflow.py

"""
E2E ワークフロー: Knowledge Hub → RAG → AI Judge → Exchange

PoC Pivot の中心となるオーケストレーション。
"""

import logging
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.ai.schemas import RAGContext, TradeAction
from app.ai.service import AIService
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import WorkflowRunResult, WorkflowStepError
from app.exchange.schemas import OrderRequest, OrderResult, OrderStatus
from app.exchange.service import ExchangeService
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeSearchRequest,
)
from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Workflow processing error."""


def check_rule_engine(
    monitoring_service: Optional[MonitoringService] = None,
) -> Tuple[bool, str]:
    """Check rule engine constraints before LLM call.

    Returns (can_trade, reason).
    Rule engine runs BEFORE LLM to save cost (CLAUDE.md execution order).

    Check order (most specific first):
    1. HF below threshold (hf_below_threshold)
    2. Generic emergency stop (emergency_stop)
    """
    if monitoring_service is None:
        return True, "no_monitoring"

    # Check last recorded health factor first (most specific reason)
    status = monitoring_service.get_status()
    if status.last_health_factor is not None:
        if status.last_health_factor < Decimal("1.6"):
            return False, "hf_below_threshold"

    # Check generic emergency stop (manual activation or other reasons)
    if not monitoring_service.is_trading_allowed():
        return False, "emergency_stop"

    return True, "ok"


class WorkflowResult:
    """Result of processing a single knowledge item."""

    def __init__(
        self,
        item_id: int,
        action: TradeAction,
        confidence: int,
        order_result: Optional[OrderResult],
        reason: str,
    ) -> None:
        self.item_id = item_id
        self.action = action
        self.confidence = confidence
        self.order_result = order_result
        self.reason = reason


def process_pending_knowledge(
    db: Session,
    *,
    knowledge_service: KnowledgeService,
    ai_service: AIService,
    exchange_service: ExchangeService,
    monitoring_service: Optional[MonitoringService] = None,
    trade_amount_usd: Decimal = Decimal("50"),
    dry_run: bool = False,
) -> WorkflowRunResult:
    """Process pending knowledge items through the full pipeline.

    Flow:
    1. Fetch pending items from Knowledge Hub
    2. Rule engine pre-check (HF, emergency stop)
    3. For each item: RAG → AI Judge → Exchange
    4. Update item status (traded/skipped/error)
    5. Return aggregated result
    """
    pending = knowledge_service.get_pending(db)

    if not pending:
        logger.info("No pending knowledge items to process")
        return WorkflowRunResult(status="no_items")

    logger.info("Processing %d pending knowledge items", len(pending))

    # Rule engine pre-check (runs BEFORE LLM to save cost)
    can_trade, rule_reason = check_rule_engine(monitoring_service)

    if not can_trade:
        logger.info("Rule engine blocked trading: %s", rule_reason)
        # Mark all items as skipped
        for item in pending:
            try:
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.SKIPPED)
            except Exception:
                logger.warning("Failed to update status for item %d", item.id)
        return WorkflowRunResult(
            fetched_count=len(pending),
            hold_count=len(pending),
            status="completed",
        )

    errors: List[WorkflowStepError] = []
    traded_count = 0
    hold_count = 0
    skipped_count = 0

    for item in pending:
        try:
            result = _process_single_item(
                db,
                item,
                knowledge_service=knowledge_service,
                ai_service=ai_service,
                exchange_service=exchange_service,
                trade_amount_usd=trade_amount_usd,
                dry_run=dry_run,
            )

            if (
                result.order_result is not None
                and result.order_result.status == OrderStatus.SUCCESS
            ):
                traded_count += 1
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.ANALYZED)
            elif result.action == TradeAction.HOLD:
                hold_count += 1
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.SKIPPED)
            else:
                skipped_count += 1
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.SKIPPED)
        except Exception as exc:
            logger.error("Failed to process item %d: %s", item.id, exc)
            errors.append(
                WorkflowStepError(
                    item_id=item.id,
                    step="pipeline",
                    message=str(exc)[:200],
                )
            )
            try:
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.ERROR)
            except Exception as update_exc:
                logger.error("Failed to update error status for item %d: %s", item.id, update_exc)

    status = "completed"
    if errors:
        status = (
            "completed_with_errors" if (traded_count + hold_count + skipped_count) > 0 else "failed"
        )

    logger.info(
        "Workflow completed: fetched=%d, traded=%d, hold=%d, skipped=%d, errors=%d",
        len(pending),
        traded_count,
        hold_count,
        skipped_count,
        len(errors),
    )

    return WorkflowRunResult(
        fetched_count=len(pending),
        analyzed_count=traded_count + hold_count + skipped_count,
        traded_count=traded_count,
        skipped_count=skipped_count,
        hold_count=hold_count,
        errors=errors,
        status=status,
    )


def _process_single_item(
    db: Session,
    item: KnowledgeItem,
    *,
    knowledge_service: KnowledgeService,
    ai_service: AIService,
    exchange_service: ExchangeService,
    trade_amount_usd: Decimal,
    dry_run: bool,
) -> WorkflowResult:
    """Process a single knowledge item through the full pipeline."""
    # 1. RAG search
    query = item.title or item.source_url or "analyze market conditions"
    search_request = KnowledgeSearchRequest(query=query, top_k=5)
    search_results = knowledge_service.search(db, search_request)

    rag_context = RAGContext(
        chunks=[r.content for r in search_results],
        query=query,
        source_count=len(search_results),
    )

    # 2. AI Two-Phase judge
    cross_result = ai_service.judge_with_rag(query, rag_context)
    action = cross_result.final_action
    confidence = cross_result.final_confidence
    reason = cross_result.final_reason or ""

    logger.info(
        "AI judge for item %d: action=%s, confidence=%d, agreed=%s",
        item.id,
        action.value,
        confidence,
        cross_result.agreed,
    )

    # 3. Execute trade if applicable
    order_result: Optional[OrderResult] = None
    if action in (TradeAction.BUY, TradeAction.SELL) and confidence >= 40:
        order_request = OrderRequest(
            action=action,
            amount_usd=trade_amount_usd,
            reason=reason,
            dry_run=dry_run,
        )
        order_result = exchange_service.execute_trade(order_request)
        logger.info(
            "Trade for item %d: status=%s, order_id=%s",
            item.id,
            order_result.status.value,
            order_result.order_id,
        )
    else:
        logger.info(
            "Skip trade for item %d: action=%s, confidence=%d", item.id, action.value, confidence
        )

    return WorkflowResult(
        item_id=item.id,
        action=action,
        confidence=confidence,
        order_result=order_result,
        reason=reason,
    )
