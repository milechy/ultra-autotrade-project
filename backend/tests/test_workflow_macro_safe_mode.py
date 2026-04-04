# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for MacroSafeMode wiring in process_pending_knowledge."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.ai.schemas import (
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.automation.macro_safe_mode import SafeModeStatus
from app.automation.workflow import process_pending_knowledge
from app.exchange.schemas import OrderResult, OrderStatus
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
)


def _make_item(item_id: int = 1) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title="BTC News",
        item_type=KnowledgeItemType.TEXT,
        raw_text="Bitcoin surges",
        status="pending",
        chunk_count=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_cross_result(action: TradeAction = TradeAction.HOLD) -> CrossValidationResult:
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=60,
        reason="test",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=60,
        final_reason="test",
    )


def _make_knowledge_service(items: list) -> MagicMock:
    svc = MagicMock()
    svc.get_pending.return_value = items
    svc.search.return_value = []
    svc.update_status.return_value = None
    return svc


def _make_ai_service(action: TradeAction = TradeAction.HOLD) -> MagicMock:
    svc = MagicMock()
    svc.judge_with_rag.return_value = _make_cross_result(action)
    return svc


def _make_exchange_service() -> MagicMock:
    svc = MagicMock()
    svc.execute_trade.return_value = OrderResult(
        order_id="test-001",
        status=OrderStatus.SUCCESS,
        side="buy",
        symbol="BTC/USDT",
        amount_usd=Decimal("50"),
        price=Decimal("100000"),
        message="ok",
        timestamp=datetime.now(timezone.utc),
    )
    return svc


class TestMacroSafeModeWiring:
    """MacroSafeMode integration tests for process_pending_knowledge."""

    def test_macro_safe_mode_active_skips_all_items(self):
        """MacroSafeMode active → all items SKIPPED, traded_count=0."""
        items = [_make_item(1), _make_item(2)]
        knowledge_svc = _make_knowledge_service(items)
        ai_svc = _make_ai_service()
        exchange_svc = _make_exchange_service()
        db = MagicMock()

        active_status = SafeModeStatus(
            active=True,
            reason="within FOMC 2026-05 window",
        )

        with patch(
            "app.automation.macro_safe_mode.MacroSafeMode",
            return_value=MagicMock(is_safe_mode_active=MagicMock(return_value=active_status)),
        ):
            result = process_pending_knowledge(
                db,
                knowledge_service=knowledge_svc,
                ai_service=ai_svc,
                exchange_service=exchange_svc,
            )

        assert result.fetched_count == 2
        assert result.hold_count == 2
        assert result.traded_count == 0
        assert result.status == "completed"
        # AI judge must NOT be called
        ai_svc.judge_with_rag.assert_not_called()
        # All items should be updated to SKIPPED
        assert knowledge_svc.update_status.call_count == 2
        calls = [call.args[2] for call in knowledge_svc.update_status.call_args_list]
        assert all(s == KnowledgeItemStatus.SKIPPED for s in calls)

    def test_macro_safe_mode_inactive_continues_normal_flow(self):
        """MacroSafeMode inactive → normal flow continues (AI judge called)."""
        items = [_make_item(1)]
        knowledge_svc = _make_knowledge_service(items)
        ai_svc = _make_ai_service(TradeAction.HOLD)
        exchange_svc = _make_exchange_service()
        db = MagicMock()

        inactive_status = SafeModeStatus(
            active=False,
            reason="no active macro event window",
        )

        with patch(
            "app.automation.macro_safe_mode.MacroSafeMode",
            return_value=MagicMock(is_safe_mode_active=MagicMock(return_value=inactive_status)),
        ):
            result = process_pending_knowledge(
                db,
                knowledge_service=knowledge_svc,
                ai_service=ai_svc,
                exchange_service=exchange_svc,
            )

        # AI judge should have been called
        ai_svc.judge_with_rag.assert_called_once()
        # No items should have been traded (HOLD)
        assert result.traded_count == 0

    def test_macro_safe_mode_exception_continues_normal_flow(self):
        """MacroSafeMode raises exception → log warning, continue normal flow (do not block)."""
        items = [_make_item(1)]
        knowledge_svc = _make_knowledge_service(items)
        ai_svc = _make_ai_service(TradeAction.HOLD)
        exchange_svc = _make_exchange_service()
        db = MagicMock()

        with patch(
            "app.automation.macro_safe_mode.MacroSafeMode",
            side_effect=RuntimeError("unexpected error"),
        ):
            result = process_pending_knowledge(
                db,
                knowledge_service=knowledge_svc,
                ai_service=ai_svc,
                exchange_service=exchange_svc,
            )

        # Normal flow continues despite exception
        ai_svc.judge_with_rag.assert_called_once()
        assert result.status in ("completed", "completed_with_errors")
