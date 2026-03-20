# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_e2e_workflow.py
"""E2E workflow integration tests."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.ai.schemas import (
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.ai.service import AIService
from app.automation.schemas import WorkflowRunResult
from app.automation.workflow import process_pending_knowledge
from app.exchange.client import DummyExchangeClient
from app.exchange.service import ExchangeService
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
    KnowledgeSearchResult,
)


def _make_item(item_id=1, title="BTC News", status=KnowledgeItemStatus.PENDING):
    return KnowledgeItem(
        id=item_id,
        source_url=None,
        title=title,
        raw_text="Bitcoin surges",
        status=status,
        chunk_count=3,
        item_type=KnowledgeItemType.TEXT,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_search_results():
    return [
        KnowledgeSearchResult(
            chunk_id=1,
            document_id=1,
            content="Bitcoin hits new all-time high",
            similarity=0.95,
            source_url=None,
            title="BTC News",
        )
    ]


def _make_cross_result(action, confidence, agreed=True):
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE, action=action, confidence=confidence, reason="test"
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=agreed,
        final_action=action,
        final_confidence=confidence,
        final_reason="test reason",
    )


def _make_exchange_settings():
    settings = MagicMock()
    settings.default_symbol = "BTC/USDT"
    settings.max_order_usd = Decimal("100")
    settings.daily_trade_limit = 10
    settings.cooldown_seconds = 0
    settings.sandbox = True
    return settings


class TestE2EWorkflow:
    def test_buy_flow(self):
        """Full BUY pipeline: pending -> RAG -> AI(BUY,85) -> exchange -> traded."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.traded_count == 1
        assert result.status == "completed"
        mock_ks.update_status.assert_called_once()

    def test_hold_flow(self):
        """HOLD pipeline: pending -> RAG -> AI(HOLD,50) -> skip exchange -> skipped."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.HOLD, 50)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.hold_count == 1
        assert result.traded_count == 0

    def test_disagree_defaults_hold(self):
        """Disagreement -> HOLD (fail-closed)."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        # Simulate disagreement (final=HOLD, confidence=25)
        mock_ai = MagicMock(spec=AIService)
        disagreement = _make_cross_result(TradeAction.HOLD, 25, agreed=False)
        mock_ai.judge_with_rag.return_value = disagreement

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.hold_count == 1
        assert result.traded_count == 0

    def test_error_marks_item(self):
        """Processing error -> item marked as ERROR, continue."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item(1), _make_item(2)]
        mock_ks.search.side_effect = [Exception("DB error"), _make_search_results()]

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.HOLD, 50)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 2
        # First item errored, second item processed normally (HOLD)
        assert len(result.errors) == 1
        assert result.errors[0].item_id == 1
        assert result.hold_count == 1
        assert result.status == "completed_with_errors"

    def test_no_pending_items(self):
        """No pending items -> no_items status."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = []

        mock_ai = MagicMock(spec=AIService)
        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.status == "no_items"
        assert result.fetched_count == 0

    def test_dry_run(self):
        """Dry run: trade should be skipped (order_result.status == SKIPPED)."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            dry_run=True,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        # Dry run returns OrderResult with SKIPPED status → order_result is not None
        # but the trade itself didn't execute → counted as skipped_count
        assert result.traded_count == 0
        assert result.skipped_count == 1

    def test_sell_flow(self):
        """Full SELL pipeline: pending -> RAG -> AI(SELL,80) -> exchange -> traded."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.SELL, 80)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.traded_count == 1
        assert result.status == "completed"

    def test_low_confidence_buy_skips_trade(self):
        """BUY with confidence < 40 should not trigger trade (per workflow logic)."""
        mock_db = MagicMock()
        mock_ks = MagicMock()
        mock_ks.get_pending.return_value = [_make_item()]
        mock_ks.search.return_value = _make_search_results()

        mock_ai = MagicMock(spec=AIService)
        # confidence=30 is below the 40 threshold in _process_single_item
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 30)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.traded_count == 0
        assert len(client.orders) == 0