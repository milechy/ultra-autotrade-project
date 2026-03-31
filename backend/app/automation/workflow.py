# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/workflow.py

"""
E2E workflow: Knowledge Hub → RAG → AI Judge → Exchange

Central orchestration for the PoC Pivot.
Also maintains the legacy Notion → AI → OctoBot flow (WorkflowService).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.ai.judgment_log import JudgmentRecord, get_judgment_logger
from app.ai.schemas import AIAnalysisResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import ComponentType, WorkflowRunResult, WorkflowStepError
from app.automation.shadow_mode_service import ShadowModeService
from app.bots.schemas import (
    OctoBotSignal,
    OctoBotSignalRequest,
    OctoBotSignalResponse,
    OctoBotSignalStatus,
)
from app.bots.service import OctoBotService
from app.data_feeds.context import build_market_context
from app.exchange.schemas import OrderRequest, OrderResult, OrderStatus
from app.exchange.service import ExchangeService
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeSearchRequest,
)
from app.knowledge.service import KnowledgeService
from app.notion.service import NotionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared dataclass: WorkflowResult (used by automation_router.py / legacy flow)
# ---------------------------------------------------------------------------


@dataclass
class WorkflowResult:
    """Summary of workflow execution result (legacy Notion→AI→OctoBot flow)."""

    fetched_count: int = 0
    analyzed_count: int = 0
    octobot_success_count: int = 0
    octobot_skipped_count: int = 0
    octobot_failed_count: int = 0
    notion_updated_count: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy flow: WorkflowService (Notion → AI → OctoBot → Notion)
# ---------------------------------------------------------------------------


class WorkflowService:
    """
    Orchestrator for Notion → AI → OctoBot → Notion write-back flow.

    Services are injected via constructor to enable dependency injection.
    """

    def __init__(
        self,
        notion_service: NotionService,
        ai_service: AIService,
        octobot_service: OctoBotService,
    ) -> None:
        self._notion = notion_service
        self._ai = ai_service
        self._octobot = octobot_service

    def process_pending_news(self) -> WorkflowResult:
        """
        Fetch unprocessed news items and run AI judgment → OctoBot send → Notion write-back.

        Returns:
            WorkflowResult: Summary of processing results
        """
        errors: List[str] = []
        fetched_count = 0
        analyzed_count = 0
        octobot_success = 0
        octobot_skipped = 0
        octobot_failed = 0
        notion_updated = 0

        # 1. Fetch unprocessed news from Notion
        logger.info("Workflow: fetching unprocessed news from Notion")
        try:
            news_items = self._notion.fetch_unprocessed_news()
            fetched_count = len(news_items)
            logger.info("Workflow: fetched %d unprocessed news items", fetched_count)
        except Exception as exc:
            error_msg = f"Failed to fetch news from Notion: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            return WorkflowResult(
                fetched_count=0,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=errors,
            )

        if fetched_count == 0:
            logger.info("Workflow: no unprocessed news to process")
            return WorkflowResult(
                fetched_count=0,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=[],
            )

        # 2. AI judgment
        logger.info("Workflow: analyzing %d news items with AI", fetched_count)
        try:
            ai_results = self._ai.analyze_items(news_items)
            analyzed_count = len(ai_results)
            logger.info("Workflow: AI analyzed %d items", analyzed_count)
        except Exception as exc:
            error_msg = f"AI analysis failed: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            return WorkflowResult(
                fetched_count=fetched_count,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=errors,
            )

        # 3. Send signals to OctoBot
        failed_signal_ids: dict[str, str] = {}
        response: Optional[OctoBotSignalResponse] = None

        signals = self._convert_to_octobot_signals(ai_results)
        if signals:
            logger.info("Workflow: sending %d signals to OctoBot", len(signals))
            try:
                request = OctoBotSignalRequest(signals=signals, count=len(signals))
                response = self._octobot.process_signals(request)
                octobot_success = response.success_count
                octobot_skipped = response.skipped_count
                octobot_failed = response.failed_count
                logger.info(
                    "Workflow: OctoBot result - sent=%d, skipped=%d, failed=%d",
                    octobot_success,
                    octobot_skipped,
                    octobot_failed,
                )

                for detail in response.details:
                    if detail.status == OctoBotSignalStatus.FAILED:
                        failed_signal_ids[detail.id] = detail.message or "OctoBot send failed"
                        logger.warning(
                            "OctoBot signal failed: id=%s, message=%s",
                            detail.id,
                            detail.message,
                        )
            except Exception as exc:
                error_msg = f"OctoBot signal processing failed: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)
                octobot_failed = len(signals)
                for signal in signals:
                    failed_signal_ids[signal.id] = str(exc)
        else:
            logger.info("Workflow: no signals to send to OctoBot")

        # 4. Write results back to Notion
        logger.info("Workflow: updating Notion with AI results")
        for result in ai_results:
            try:
                if result.id in failed_signal_ids:
                    self._notion.update_item_with_error(
                        page_id=result.id,
                        error_message=failed_signal_ids[result.id],
                        action=result.action.value,
                        confidence=result.confidence,
                    )
                    logger.info(
                        "Notion page marked as error for retry: page_id=%s",
                        result.id,
                    )
                else:
                    self._notion.update_item_with_ai_result(
                        page_id=result.id,
                        action=result.action.value,
                        confidence=result.confidence,
                        sentiment=result.sentiment,
                        summary=result.summary,
                    )
                notion_updated += 1
            except Exception as exc:
                error_msg = f"Failed to update Notion page {result.id}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

        logger.info(
            "Workflow: completed - fetched=%d, analyzed=%d, octobot_sent=%d, notion_updated=%d",
            fetched_count,
            analyzed_count,
            octobot_success,
            notion_updated,
        )

        return WorkflowResult(
            fetched_count=fetched_count,
            analyzed_count=analyzed_count,
            octobot_success_count=octobot_success,
            octobot_skipped_count=octobot_skipped,
            octobot_failed_count=octobot_failed,
            notion_updated_count=notion_updated,
            errors=errors,
        )

    def _convert_to_octobot_signals(
        self, ai_results: List[AIAnalysisResult]
    ) -> List[OctoBotSignal]:
        """Convert AIAnalysisResult to OctoBotSignal. HOLD actions are skipped."""
        signals: List[OctoBotSignal] = []

        for result in ai_results:
            if result.action == TradeAction.HOLD:
                logger.debug("Skipping HOLD signal for id=%s", result.id)
                continue

            signal = OctoBotSignal(
                id=result.id,
                url=result.url,
                action=result.action,
                confidence=result.confidence,
                reason=result.reason or "Signal generated by AI judgment",
                timestamp=result.timestamp,
            )
            signals.append(signal)

        return signals


# ---------------------------------------------------------------------------
# New PoC flow: Knowledge Hub → RAG → AI Judge → Exchange
# ---------------------------------------------------------------------------


class WorkflowError(Exception):
    """Workflow processing error."""


class _SingleItemResult:
    """Result of processing a single knowledge item (internal use)."""

    def __init__(
        self,
        item_id: int,
        action: TradeAction,
        confidence: int,
        order_result: Optional[OrderResult],
        reason: str,
        shadow_logged: bool = False,
        proposed: bool = False,
    ) -> None:
        self.item_id = item_id
        self.action = action
        self.confidence = confidence
        self.order_result = order_result
        self.reason = reason
        self.shadow_logged = shadow_logged
        self.proposed = proposed


def check_rule_engine(
    monitoring_service: Optional[MonitoringService] = None,
    *,
    daily_traded_usd: Optional[Decimal] = None,
    total_assets_usd: Optional[Decimal] = None,
) -> Tuple[bool, str]:
    """Check rule engine constraints before LLM call.

    Returns (can_trade, reason).
    Rule engine runs BEFORE LLM to save cost (CLAUDE.md execution order).

    Check order (most specific first):
    1. HF below threshold (hf_below_threshold)
    2. Daily 30% limit reached (daily_limit_reached)
    3. Generic emergency stop (emergency_stop)
    """
    if monitoring_service is None:
        return True, "no_monitoring"

    status = monitoring_service.get_status()
    if status.last_health_factor is not None:
        if status.last_health_factor < Decimal("1.6"):
            return False, "hf_below_threshold"

    # Execution Order #3: daily limit 30% reached? → HOLD
    if (
        daily_traded_usd is not None
        and total_assets_usd is not None
        and total_assets_usd > Decimal("0")
    ):
        daily_limit = total_assets_usd * Decimal("30") / Decimal("100")
        if daily_traded_usd >= daily_limit:
            return False, "daily_limit_reached"

    if not monitoring_service.is_trading_allowed():
        return False, "emergency_stop"

    return True, "ok"


def process_pending_knowledge(
    db: Session,
    *,
    knowledge_service: KnowledgeService,
    ai_service: AIService,
    exchange_service: ExchangeService,
    monitoring_service: Optional[MonitoringService] = None,
    shadow_mode_service: Optional[ShadowModeService] = None,
    trade_amount_usd: Decimal = Decimal("50"),
    dry_run: bool = False,
    execution_policy: str = "auto_execute",
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

    # Refresh HF and record in MonitoringService (used for rule engine decision)
    hf: Optional[Decimal] = None  # Initialize before try block
    if monitoring_service is not None:
        try:
            from app.aave.monitor import get_health_factor as _aave_get_hf  # noqa: PLC0415

            hf = _aave_get_hf()
            if hf is not None:
                monitoring_service.record_health_factor(hf)
        except Exception as _exc:  # noqa: BLE001
            logger.warning("Failed to refresh health factor from Aave: %s", _exc)

    can_trade, rule_reason = check_rule_engine(monitoring_service)

    if not can_trade:
        logger.info("Rule engine blocked trading: %s", rule_reason)
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
    shadow_logged_count = 0
    proposed_count = 0

    # HF emergency override: always auto_execute if HF < 1.6
    effective_policy = execution_policy
    if hf is not None and hf < Decimal("1.6"):
        effective_policy = "auto_execute"
        logger.info("HF emergency override: execution_policy forced to auto_execute (hf=%s)", hf)

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
                shadow_mode_service=shadow_mode_service,
                health_factor=hf,
                execution_policy=effective_policy,
            )

            if result.shadow_logged:
                # Shadow Mode: record only, no actual trade
                shadow_logged_count += 1
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.SKIPPED)
            elif result.proposed:
                proposed_count += 1
                knowledge_service.update_status(db, item.id, KnowledgeItemStatus.SKIPPED)
            elif (
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
            # Record in error rate monitor
            if monitoring_service is not None:
                try:
                    monitoring_service.record_error(ComponentType.SYSTEM)
                except Exception as _exc:  # noqa: BLE001
                    logger.debug("record_error failed: %s", _exc)
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
        "Workflow completed: fetched=%d, traded=%d, hold=%d, skipped=%d, "
        "shadow=%d, proposed=%d, errors=%d",
        len(pending),
        traded_count,
        hold_count,
        skipped_count,
        shadow_logged_count,
        proposed_count,
        len(errors),
    )

    return WorkflowRunResult(
        fetched_count=len(pending),
        analyzed_count=traded_count + hold_count + skipped_count + shadow_logged_count,
        traded_count=traded_count,
        skipped_count=skipped_count,
        hold_count=hold_count,
        shadow_logged_count=shadow_logged_count,
        proposed_count=proposed_count,
        errors=errors,
        status=status,
    )


def _create_proposal_from_judgment(
    db: Session,
    item_id: int,
    action: TradeAction,
    reason: str,
    trade_amount_usd: Decimal,
    user_id: int = 0,
) -> None:
    """Create a pending Proposal from AI judgment (require_approval / proposal_only)."""
    from datetime import timedelta  # noqa: PLC0415

    from app.proposals.models import Proposal  # noqa: PLC0415

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    proposal = Proposal(
        user_id=user_id,
        operation=action.value,
        asset="USDC",
        amount=trade_amount_usd,
        amount_usd=trade_amount_usd,
        reason=reason,
        status="pending",
        expires_at=expires_at,
    )
    db.add(proposal)
    db.flush()
    logger.info(
        "Proposal created: item_id=%d, action=%s, expires_at=%s",
        item_id,
        action.value,
        expires_at,
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
    shadow_mode_service: Optional[ShadowModeService] = None,
    health_factor: Optional[Decimal] = None,
    execution_policy: str = "auto_execute",
) -> _SingleItemResult:
    """Process a single knowledge item through the full pipeline."""
    query = item.title or item.source_url or "analyze market conditions"
    search_request = KnowledgeSearchRequest(query=query, top_k=5)
    search_results = knowledge_service.search(db, search_request)

    rag_context = RAGContext(
        chunks=[r.content for r in search_results],
        query=query,
        source_count=len(search_results),
    )

    ctx = build_market_context(health_factor=health_factor)
    _judgment_logger = get_judgment_logger()
    _cognitive = _judgment_logger.get_cognitive_state()
    cross_result = ai_service.judge_with_rag(
        query, rag_context, market_context=ctx, cognitive_state=_cognitive
    )
    action = cross_result.final_action
    confidence = cross_result.final_confidence
    reason = cross_result.final_reason or ""

    _judgment_logger.record_nowait(
        JudgmentRecord(
            action=action.value,
            confidence=confidence,
            reason=reason,
            primary_action=cross_result.primary.action.value,
            secondary_action=cross_result.secondary.action.value
            if cross_result.secondary
            else None,
            agreed=cross_result.agreed,
        )
    )

    logger.info(
        "AI judge for item %d: action=%s, confidence=%d, agreed=%s",
        item.id,
        action.value,
        confidence,
        cross_result.agreed,
    )

    # Shadow Mode: record only, skip actual trade
    if shadow_mode_service is not None and shadow_mode_service.is_enabled():
        shadow_mode_service.record(cross_result, str(item.id))
        logger.info("Shadow Mode: recorded item %d, skipping actual trade", item.id)
        return _SingleItemResult(
            item_id=item.id,
            action=action,
            confidence=confidence,
            order_result=None,
            reason=reason,
            shadow_logged=True,
        )

    order_result: Optional[OrderResult] = None
    if action in (TradeAction.BUY, TradeAction.SELL) and confidence >= 40:
        if execution_policy in ("require_approval", "proposal_only"):
            _create_proposal_from_judgment(
                db,
                item_id=item.id,
                action=action,
                reason=reason,
                trade_amount_usd=trade_amount_usd,
            )
            return _SingleItemResult(
                item_id=item.id,
                action=action,
                confidence=confidence,
                order_result=None,
                reason=reason,
                proposed=True,
            )
        # auto_execute: proceed with immediate trade
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

    return _SingleItemResult(
        item_id=item.id,
        action=action,
        confidence=confidence,
        order_result=order_result,
        reason=reason,
    )
