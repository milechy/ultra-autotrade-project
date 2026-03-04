# backend/app/automation/workflow.py

"""
E2E ワークフロー: Knowledge Hub → RAG → AI Judge → Exchange

PoC Pivot の中心となるオーケストレーション。
"""

import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ai.schemas import RAGContext, TradeAction
from app.ai.service import AIService
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
    trade_amount_usd: Decimal = Decimal("50"),
    dry_run: bool = False,
) -> List[WorkflowResult]:
    """
    Main E2E workflow. For each pending knowledge item:
    1. RAG search for context
    2. AI Two-Phase judge
    3. Execute trade if BUY/SELL with confidence >= 40
    4. Update status

    Fail-closed: errors mark item as 'error' and continue.
    """
    results: List[WorkflowResult] = []

    pending_items = knowledge_service.get_pending(db)
    if not pending_items:
        logger.info("No pending knowledge items to process")
        return results

    logger.info("Processing %d pending knowledge items", len(pending_items))

    for item in pending_items:
        try:
            result = _process_single_item(
                db=db,
                item=item,
                knowledge_service=knowledge_service,
                ai_service=ai_service,
                exchange_service=exchange_service,
                trade_amount_usd=trade_amount_usd,
                dry_run=dry_run,
            )
            results.append(result)
        except Exception as exc:
            logger.error("Failed to process item %d: %s", item.id, exc)
            try:
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.ERROR)
            except Exception as update_exc:
                logger.error("Failed to update error status for item %d: %s", item.id, update_exc)
            results.append(
                WorkflowResult(
                    item_id=item.id,
                    action=TradeAction.HOLD,
                    confidence=0,
                    order_result=None,
                    reason=f"Processing error: {exc}",
                )
            )

    logger.info(
        "Workflow completed: %d items processed, %d trades executed",
        len(results),
        sum(1 for r in results if r.order_result and r.order_result.status == OrderStatus.SUCCESS),
    )
    return results


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

    # 4. Update status
    knowledge_service.update_status(db, item.id, KnowledgeItemStatus.ANALYZED)

    return WorkflowResult(
        item_id=item.id,
        action=action,
        confidence=confidence,
        order_result=order_result,
        reason=reason,
    )
