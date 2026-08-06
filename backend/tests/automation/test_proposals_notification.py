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

import json
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
    _deliver_ai_proposal_push,
)
from app.automation.workflow import _create_proposal_from_judgment
from app.notifications.schemas import NotificationMessage
from app.notifications.templates import ai_proposal_notification


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

    def test_skip_reason_notification_when_should_trade_false(self) -> None:
        """DynamicFee should_trade=False: 提案は作らないが、スキップ理由を本人に通知する。

        2026-08-06 (Asana 1217210854320785): 以前は「何も送らない」が期待値だったが、
        それが「無音デッドゾーン」（残高はあるのに理由が分からず提案が来ない）の
        原因の一つだった。採算ゲート未達時も理由を本人に通知するよう変更。
        """
        _, msgs = self._run(should_trade=False, user_id=42)
        assert len(msgs) == 1
        assert msgs[0].user_id == 42

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


class TestDeliverAiProposalPush:
    """_deliver_ai_proposal_push: Web Push実配信 + notification_logs delivered記録 (PR5)。"""

    @staticmethod
    def _payload() -> Any:
        return ai_proposal_notification("SUPPLY", "USDC", Decimal("100"), 80)

    @staticmethod
    def _db_with_push_enabled_user(user_id: int) -> MagicMock:
        """通知設定で Push を有効化済みのユーザーを返す db モック。

        2026-08-05: 配信前に notification_settings_json を見る設定ゲート (B-N4) が
        入ったため、配信されることを確認するテストでは明示的に有効化しておく必要がある。
        """
        user = MagicMock()
        user.id = user_id
        user.notification_settings_json = json.dumps(
            {"push_enabled": True, "preferences": {"ai_proposal": True}}
        )
        db = MagicMock()
        db.get.return_value = user
        return db

    def test_vapid_unset_records_as_undelivered(self) -> None:
        """VAPID未設定時は例外を投げず、かつ delivered=False として記録すること。

        2026-08-06 変更: 以前は「静かにスキップし push 行を作らない」ことを
        期待していたが、それだと「届かなかった」事実が notification_logs に残らず、
        到達率 (受け入れ条件 B-4) が「送れたものだけ」を母数に計算されて実態より
        良く見えてしまう。本番で降格通知が届いていないことをログから判別できなかった
        原因でもある。未到達も記録する。
        """
        mock_db = self._db_with_push_enabled_user(1)
        with patch("app.notifications.push.get_vapid_config", return_value=None):
            result = _deliver_ai_proposal_push(mock_db, 1, self._payload())

        assert result is False, "未到達なので False を返すこと"
        mock_db.add.assert_called_once()
        logged = mock_db.add.call_args.args[0]
        assert logged.channel == "push"
        assert logged.delivered is False

    def test_vapid_set_success_logs_delivered_true(self) -> None:
        """配信成功: delivered=True の push NotificationLog が1行追加される。"""
        mock_db = self._db_with_push_enabled_user(5)
        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = True
        with (
            patch("app.notifications.push.get_vapid_config", return_value=MagicMock()),
            patch("app.notifications.push.WebPushSender", return_value=mock_sender),
            patch("app.notifications.push.DatabaseSubscriptionStore"),
        ):
            _deliver_ai_proposal_push(mock_db, 5, self._payload())

        mock_db.add.assert_called_once()
        added = mock_db.add.call_args.args[0]
        assert added.channel == "push"
        assert added.delivered is True
        assert added.user_id == 5

    def test_vapid_set_failure_logs_delivered_false(self) -> None:
        """配信失敗: delivered=False の push NotificationLog が1行追加される。"""
        mock_db = self._db_with_push_enabled_user(5)
        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = False
        with (
            patch("app.notifications.push.get_vapid_config", return_value=MagicMock()),
            patch("app.notifications.push.WebPushSender", return_value=mock_sender),
            patch("app.notifications.push.DatabaseSubscriptionStore"),
        ):
            _deliver_ai_proposal_push(mock_db, 5, self._payload())

        added = mock_db.add.call_args.args[0]
        assert added.channel == "push"
        assert added.delivered is False

    def test_exception_does_not_raise(self) -> None:
        """内部例外は握りつぶし、呼び出し元に伝播しない (fail-open)。"""
        mock_db = MagicMock()
        with patch("app.notifications.push.get_vapid_config", side_effect=RuntimeError("boom")):
            _deliver_ai_proposal_push(mock_db, 1, self._payload())  # must not raise
        mock_db.add.assert_not_called()


class TestCreateProposalsForUsersPushWiring:
    """_create_proposals_for_users が _deliver_ai_proposal_push を正しく配線していること。"""

    def test_push_delivery_called_with_user_id(self) -> None:
        user = _make_user(user_id=55)
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
                return_value=_make_fee(True),
            ),
            patch("app.notifications.factory.get_notification_service"),
            patch("app.automation.ai_judgment_scheduler._deliver_ai_proposal_push") as mock_push,
        ):
            _create_proposals_for_users(mock_db, decision, result)

        mock_push.assert_called_once()
        args = mock_push.call_args.args
        assert args[0] is mock_db
        assert args[1] == 55

    def test_push_delivery_exception_does_not_abort_proposal_creation(self) -> None:
        """push配線側で予期しない例外が出ても Proposal 作成カウントは維持される。"""
        user = _make_user(user_id=56)
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
                return_value=_make_fee(True),
            ),
            patch("app.notifications.factory.get_notification_service"),
            patch(
                "app.automation.ai_judgment_scheduler._deliver_ai_proposal_push",
                side_effect=RuntimeError("push down"),
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
