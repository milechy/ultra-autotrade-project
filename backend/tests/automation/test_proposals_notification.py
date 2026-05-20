# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/automation/test_proposals_notification.py
"""
ai_proposal_notification wiring test.

Verifies that _create_proposals_for_users() and _create_proposal_from_judgment()
both call get_notification_service().send() with a NotificationMessage where
notification_message.user_id is set correctly.

Regression guard: legacy LINE_NOTIFY_TOKEN route must not be called.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from app.ai.schemas import CrossValidationResult, LLMDecision, LLMProvider, TradeAction
from app.auth.constants import ExecutionPolicy
from app.auth.models import InvestmentTier
from app.automation.ai_judgment_scheduler import (
    _PROPOSAL_AMOUNT_MAX_USD,
    _PROPOSAL_AMOUNT_MIN_USD,
    _PROPOSAL_RATIO,
    _create_proposals_for_users,
)
from app.automation.workflow import _create_proposal_from_judgment
from app.notifications.schemas import NotificationMessage


def _make_cross_result(action: TradeAction, confidence: int = 70) -> CrossValidationResult:
    prim = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=confidence,
        reason="test reason",
        raw_response="{}",
    )
    return CrossValidationResult(
        primary=prim,
        secondary=None,
        final_action=action,
        final_confidence=confidence,
        final_reason="test reason",
        agreed=True,
    )


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.is_active = True
    user.execution_policy = ExecutionPolicy.REQUIRE_APPROVAL.value
    user.tier = InvestmentTier.LOWER.value
    user.last_judgment_at = None
    return user


def _make_decision(decision_id: int = 99) -> MagicMock:
    dec = MagicMock()
    dec.id = decision_id
    return dec


def _make_fee(should_trade: bool = True) -> MagicMock:
    fee = MagicMock()
    fee.should_trade = should_trade
    fee.fee_rate = Decimal("0.01")
    fee.fee_amount = Decimal("10")
    fee.reason = "test"
    return fee


class TestCreateProposalsForUsersNotification:
    """_create_proposals_for_users sends a notification per user."""

    def _run(
        self,
        action: TradeAction = TradeAction.BUY,
        confidence: int = 70,
        should_trade: bool = True,
        user_id: int = 42,
    ) -> tuple[MagicMock, list[Any]]:
        user = _make_user(user_id=user_id)
        decision = _make_decision()
        result = _make_cross_result(action, confidence)

        mock_db = MagicMock()
        mock_db.scalars.return_value.all.return_value = [user]

        sent_msgs: list[Any] = []

        with (
            patch(
                "app.automation.ai_judgment_scheduler._resolve_proposal_amount",
                return_value=Decimal("460"),
            ),
            patch(
                "app.fees.trade_gate.calculate_fee_by_market",
                return_value=_make_fee(should_trade),
            ),
            patch("app.notifications.factory.get_notification_service") as mock_get_svc,
        ):
            mock_svc = MagicMock()
            mock_svc.send.side_effect = lambda m: sent_msgs.append(m)
            mock_get_svc.return_value = mock_svc
            _create_proposals_for_users(mock_db, decision, result)

        return mock_svc.send, sent_msgs

    def test_send_called_once_for_one_user(self) -> None:
        """BUY: one notification per user."""
        _, msgs = self._run(action=TradeAction.BUY)
        assert len(msgs) == 1

    def test_notification_message_type(self) -> None:
        """send() receives a NotificationMessage."""
        _, msgs = self._run(action=TradeAction.BUY)
        assert isinstance(msgs[0], NotificationMessage)

    def test_notification_user_id_set(self) -> None:
        """notification_message.user_id equals user.id."""
        _, msgs = self._run(action=TradeAction.BUY, user_id=42)
        assert msgs[0].user_id == 42

    def test_no_send_when_should_trade_false(self) -> None:
        """DynamicFee should_trade=False: no notification."""
        _, msgs = self._run(should_trade=False)
        assert len(msgs) == 0

    def test_send_called_for_sell_action(self) -> None:
        """SELL: notification is also sent."""
        _, msgs = self._run(action=TradeAction.SELL)
        assert len(msgs) == 1

    def test_notification_failure_does_not_raise(self) -> None:
        """Notification failure must not abort Proposal creation."""
        user = _make_user(user_id=7)
        decision = _make_decision()
        result = _make_cross_result(TradeAction.BUY)
        mock_db = MagicMock()
        mock_db.scalars.return_value.all.return_value = [user]

        with (
            patch(
                "app.automation.ai_judgment_scheduler._resolve_proposal_amount",
                return_value=Decimal("460"),
            ),
            patch(
                "app.fees.trade_gate.calculate_fee_by_market",
                return_value=_make_fee(should_trade=True),
            ),
            patch(
                "app.notifications.factory.get_notification_service",
                side_effect=RuntimeError("notification failure"),
            ),
        ):
            count = _create_proposals_for_users(mock_db, decision, result)

        assert count == 1


class TestCreateProposalFromJudgmentNotification:
    """_create_proposal_from_judgment sends a notification via get_notification_service()."""

    def _run(
        self,
        user_id: int = 10,
        action: TradeAction = TradeAction.BUY,
    ) -> tuple[MagicMock, list[Any]]:
        mock_db = MagicMock()
        sent_msgs: list[Any] = []

        with patch("app.notifications.factory.get_notification_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.send.side_effect = lambda m: sent_msgs.append(m)
            mock_get_svc.return_value = mock_svc
            _create_proposal_from_judgment(
                db=mock_db,
                item_id=1,
                action=action,
                reason="test",
                trade_amount_usd=Decimal("1000"),
                user_id=user_id,
            )

        return mock_svc.send, sent_msgs

    def test_send_called_once(self) -> None:
        """send() is called exactly once."""
        _, msgs = self._run()
        assert len(msgs) == 1

    def test_notification_message_type(self) -> None:
        """send() receives a NotificationMessage."""
        _, msgs = self._run()
        assert isinstance(msgs[0], NotificationMessage)

    def test_notification_user_id_set(self) -> None:
        """notification_message.user_id equals argument user_id."""
        _, msgs = self._run(user_id=10)
        assert msgs[0].user_id == 10

    def test_user_id_zero_becomes_none(self) -> None:
        """user_id=0 (default falsy) -> notification_message.user_id is None."""
        _, msgs = self._run(user_id=0)
        assert msgs[0].user_id is None

    def test_notification_failure_does_not_raise(self) -> None:
        """Notification failure must not prevent Proposal DB write."""
        mock_db = MagicMock()
        with patch(
            "app.notifications.factory.get_notification_service",
            side_effect=RuntimeError("notification failure"),
        ):
            _create_proposal_from_judgment(
                db=mock_db,
                item_id=1,
                action=TradeAction.BUY,
                reason="test",
                trade_amount_usd=Decimal("500"),
                user_id=5,
            )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_old_line_notify_not_used(self) -> None:
        """Regression guard: legacy notify_proposal_created must not be called."""
        mock_db = MagicMock()
        with (
            patch("app.notifications.factory.get_notification_service"),
            patch("app.notifications.line_notifier.notify_proposal_created") as mock_legacy,
        ):
            _create_proposal_from_judgment(
                db=mock_db,
                item_id=1,
                action=TradeAction.BUY,
                reason="test",
                trade_amount_usd=Decimal("500"),
                user_id=5,
            )
        mock_legacy.assert_not_called()


class TestDynamicProposalAmount:
    """_create_proposals_for_users uses _resolve_proposal_amount per user."""

    def _run_with_resolved_amount(self, resolved_amount: Decimal) -> "Decimal | None":
        """Runs with mocked _resolve_proposal_amount, returns amount used in Proposal.add()."""
        user = _make_user(user_id=5)
        decision = _make_decision()
        result = _make_cross_result(TradeAction.BUY)

        mock_db = MagicMock()
        mock_db.scalars.return_value.all.return_value = [user]

        added_proposals: list[Any] = []
        mock_db.add.side_effect = lambda obj: added_proposals.append(obj)

        with (
            patch(
                "app.automation.ai_judgment_scheduler._resolve_proposal_amount",
                return_value=resolved_amount,
            ),
            patch(
                "app.fees.trade_gate.calculate_fee_by_market",
                return_value=_make_fee(should_trade=True),
            ),
            patch("app.notifications.factory.get_notification_service"),
        ):
            _create_proposals_for_users(mock_db, decision, result)

        return added_proposals[0].amount_usd if added_proposals else None

    def test_uses_resolved_amount_in_proposal(self) -> None:
        """Proposal.amount_usd equals the value returned by _resolve_proposal_amount."""
        used = self._run_with_resolved_amount(Decimal("460"))
        assert used == Decimal("460")

    def test_skips_proposal_when_resolved_amount_is_zero(self) -> None:
        """When _resolve_proposal_amount returns 0, no Proposal is created."""
        used = self._run_with_resolved_amount(Decimal("0"))
        assert used is None

    def test_ratio_and_clamp_logic(self) -> None:
        """_PROPOSAL_RATIO × allocation, clamped to [MIN, MAX]."""
        allocation = Decimal("4600")
        raw = (allocation * _PROPOSAL_RATIO).quantize(Decimal("0.01"))
        expected = max(_PROPOSAL_AMOUNT_MIN_USD, min(raw, _PROPOSAL_AMOUNT_MAX_USD))
        assert expected == Decimal("460.00")
