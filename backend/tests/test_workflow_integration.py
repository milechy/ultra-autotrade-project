"""Workflow integration tests for Knowledge → RAG → AI Judge → Exchange pipeline."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.ai.schemas import (
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import WorkflowRunResult
from app.automation.workflow import check_rule_engine, process_pending_knowledge
from app.exchange.schemas import OrderResult, OrderStatus
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemType,
    KnowledgeSearchResult,
)


def _make_knowledge_item(
    item_id: int = 1,
    title: str = "BTC News",
    status: str = "pending",
) -> KnowledgeItem:
    """Create a mock KnowledgeItem."""
    return KnowledgeItem(
        id=item_id,
        title=title,
        item_type=KnowledgeItemType.TEXT,
        raw_text="Bitcoin surges past $100k",
        status=status,
        chunk_count=3,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_cross_validation(
    action: TradeAction = TradeAction.BUY,
    confidence: int = 85,
) -> CrossValidationResult:
    """Create a mock CrossValidationResult."""
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=confidence,
        reason="Strong buy signal",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=confidence,
        final_reason="Strong buy signal",
    )


def _make_order_result(status: OrderStatus = OrderStatus.SUCCESS) -> OrderResult:
    """Create a mock OrderResult."""
    return OrderResult(
        order_id="test-001",
        status=status,
        side="buy",
        symbol="BTC/USDT",
        amount_usd=Decimal("50"),
        price=Decimal("100000"),
        message="Order executed",
        timestamp=datetime.now(timezone.utc),
    )


class TestCheckRuleEngine:
    """Rule engine pre-check tests."""

    def test_no_monitoring_returns_allowed(self):
        """No monitoring service → trading allowed."""
        can_trade, reason = check_rule_engine(None)
        assert can_trade is True
        assert reason == "no_monitoring"

    def test_emergency_stop_blocks_trading(self):
        """Emergency stop active → trading blocked."""
        ms = MonitoringService(enable_state_sync=False)
        ms.activate_emergency_stop(reason="test")

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is False
        assert reason == "emergency_stop"

    def test_low_hf_blocks_trading(self):
        """HF < 1.6 → trading blocked."""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("1.5"))

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is False
        assert reason == "hf_below_threshold"

    def test_healthy_hf_allows_trading(self):
        """HF >= 1.6 → trading allowed."""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("2.0"))

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is True
        assert reason == "ok"

    def test_no_hf_recorded_allows_trading(self):
        """No HF data → trading allowed (no debt position)."""
        ms = MonitoringService(enable_state_sync=False)

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is True
        assert reason == "ok"


class TestProcessPendingKnowledge:
    """process_pending_knowledge integration tests."""

    def test_buy_flow_returns_traded(self):
        """analyzed → AI BUY → exchange → traded."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        item = _make_knowledge_item()
        ks.get_pending.return_value = [item]
        ks.search.return_value = [
            KnowledgeSearchResult(
                chunk_id=1,
                document_id=1,
                content="BTC up",
                similarity=0.9,
            )
        ]
        ai.judge_with_rag.return_value = _make_cross_validation(TradeAction.BUY, 85)
        ex.execute_trade.return_value = _make_order_result(OrderStatus.SUCCESS)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.traded_count == 1
        assert result.status == "completed"
        assert len(result.errors) == 0

    def test_hold_flow_returns_skipped(self):
        """analyzed → AI HOLD → skipped."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        item = _make_knowledge_item()
        ks.get_pending.return_value = [item]
        ks.search.return_value = [
            KnowledgeSearchResult(
                chunk_id=1,
                document_id=1,
                content="Mixed signals",
                similarity=0.7,
            )
        ]
        ai.judge_with_rag.return_value = _make_cross_validation(TradeAction.HOLD, 30)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 1
        assert result.hold_count == 1
        assert result.traded_count == 0
        assert result.status == "completed"
        ex.execute_trade.assert_not_called()

    def test_rule_engine_blocks_all_items(self):
        """HF low → all items HOLD without LLM call."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("1.4"))

        ks.get_pending.return_value = [
            _make_knowledge_item(1),
            _make_knowledge_item(2),
        ]

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
            monitoring_service=ms,
        )

        assert result.fetched_count == 2
        assert result.hold_count == 2
        assert result.traded_count == 0
        assert result.status == "completed"
        # LLM should NOT be called when rule engine blocks
        ai.judge_with_rag.assert_not_called()
        ex.execute_trade.assert_not_called()

    def test_ai_parse_failure_defaults_hold(self):
        """AI output parse failure → HOLD (parse_or_hold)."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        item = _make_knowledge_item()
        ks.get_pending.return_value = [item]
        ks.search.return_value = []
        # AI service raises error → _process_single_item should handle
        ai.judge_with_rag.side_effect = ValueError("Invalid JSON from LLM")

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].item_id == 1
        assert result.status in ("completed_with_errors", "failed")

    def test_exchange_failure_records_error(self):
        """Exchange failure → error recorded, continue."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        item = _make_knowledge_item()
        ks.get_pending.return_value = [item]
        ks.search.return_value = [
            KnowledgeSearchResult(
                chunk_id=1,
                document_id=1,
                content="BTC up",
                similarity=0.9,
            )
        ]
        ai.judge_with_rag.return_value = _make_cross_validation(TradeAction.BUY, 85)
        ex.execute_trade.side_effect = RuntimeError("Exchange connection failed")

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 1
        assert len(result.errors) == 1
        assert "Exchange connection" in result.errors[0].message

    def test_no_pending_items(self):
        """No pending items → no_items status."""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = []

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.status == "no_items"
        assert result.fetched_count == 0
