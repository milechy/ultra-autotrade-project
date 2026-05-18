# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""SlackEscalationSender / EscalationState のテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.notifications.escalation import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_ESCALATION_THRESHOLD,
    EscalationState,
    SlackEscalationSender,
)
from app.notifications.schemas import (
    NotificationChannel,
    NotificationMessage,
    NotificationSeverity,
)


def _make_message(
    severity: NotificationSeverity = NotificationSeverity.ALERT,
) -> NotificationMessage:
    return NotificationMessage(
        channel=NotificationChannel.SLACK,
        severity=severity,
        title="テストアラート",
        body="テスト本文",
    )


# ---- EscalationState テスト ----


def test_initial_consecutive_failures_is_zero() -> None:
    state = EscalationState()
    assert state.consecutive_failures == 0


def test_record_failure_increments() -> None:
    state = EscalationState()
    count = state.record_failure()
    assert count == 1
    assert state.consecutive_failures == 1


def test_record_success_resets_counter() -> None:
    state = EscalationState()
    state.record_failure()
    state.record_failure()
    state.record_success()
    assert state.consecutive_failures == 0


def test_try_escalate_first_time_returns_true() -> None:
    state = EscalationState()
    assert state.try_escalate(cooldown_minutes=30) is True


def test_try_escalate_within_cooldown_returns_false() -> None:
    state = EscalationState()
    state.try_escalate(cooldown_minutes=30)  # 初回
    # 即座に再試行 → クールダウン内
    assert state.try_escalate(cooldown_minutes=30) is False


def test_try_escalate_after_cooldown_returns_true() -> None:
    state = EscalationState()
    state.try_escalate(cooldown_minutes=30)
    # クールダウン後に直接 _last_escalation_at を過去に設定
    state._last_escalation_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    assert state.try_escalate(cooldown_minutes=30) is True


# ---- SlackEscalationSender テスト ----


class FakeSlack:
    """テスト用 Slack モック（成功固定）。"""

    def __init__(self) -> None:
        self.calls: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        self.calls.append(message)


class FailingSlack:
    """テスト用 Slack モック（常に例外）。"""

    def send(self, message: NotificationMessage) -> None:
        raise Exception("Slack unavailable")


class FakeTwilio:
    """テスト用 Twilio モック。"""

    def __init__(self) -> None:
        self.calls: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        self.calls.append(message)


def test_slack_success_resets_counter() -> None:
    """Slack 成功で連続失敗カウントがリセットされる。"""
    slack = FakeSlack()
    state = EscalationState()
    state.record_failure()
    state.record_failure()

    sender = SlackEscalationSender(
        slack_sender=slack,
        twilio_sender=None,
        state=state,
    )
    sender.send(_make_message())

    assert state.consecutive_failures == 0
    assert len(slack.calls) == 1


def test_slack_failure_increments_counter() -> None:
    """Slack 失敗で連続失敗カウントが増える。"""
    state = EscalationState()
    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=None,
        escalation_threshold=10,
        state=state,
    )
    sender.send(_make_message())

    assert state.consecutive_failures == 1


def test_escalation_triggered_after_threshold() -> None:
    """閾値到達でエスカレーションが発動する。"""
    twilio = FakeTwilio()
    state = EscalationState()

    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=twilio,
        escalation_threshold=3,
        cooldown_minutes=0,
        state=state,
    )
    for _ in range(3):
        sender.send(_make_message())

    # 3 回目で Twilio 呼び出し
    assert len(twilio.calls) == 1
    escalation_msg = twilio.calls[0]
    assert escalation_msg.severity == NotificationSeverity.EMERGENCY
    assert "3連続失敗" in escalation_msg.title


def test_escalation_not_triggered_below_threshold() -> None:
    """閾値未満ではエスカレーションしない。"""
    twilio = FakeTwilio()
    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=twilio,
        escalation_threshold=5,
        cooldown_minutes=0,
    )
    for _ in range(4):
        sender.send(_make_message())

    assert len(twilio.calls) == 0


def test_escalation_cooldown_prevents_duplicate() -> None:
    """クールダウン内は重複エスカレーションしない。"""
    twilio = FakeTwilio()
    state = EscalationState()
    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=twilio,
        escalation_threshold=3,
        cooldown_minutes=30,  # クールダウン 30 分
        state=state,
    )
    # 閾値に達する
    for _ in range(3):
        sender.send(_make_message())
    assert len(twilio.calls) == 1

    # さらに失敗してもクールダウン内は発動しない
    sender.send(_make_message())
    sender.send(_make_message())
    assert len(twilio.calls) == 1  # 追加されていない


def test_escalation_without_twilio_does_not_raise() -> None:
    """Twilio 未設定でも send() は例外を投げない。"""
    state = EscalationState()
    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=None,
        escalation_threshold=2,
        cooldown_minutes=0,
        state=state,
    )
    for _ in range(3):
        sender.send(_make_message())  # 例外が出ないこと


def test_escalation_message_contains_failure_count() -> None:
    """エスカレーションメッセージに失敗回数が含まれる。"""
    twilio = FakeTwilio()
    sender = SlackEscalationSender(
        slack_sender=FailingSlack(),
        twilio_sender=twilio,
        escalation_threshold=2,
        cooldown_minutes=0,
    )
    sender.send(_make_message())
    sender.send(_make_message())

    assert twilio.calls
    msg = twilio.calls[0]
    assert "2" in msg.title or "2" in msg.body


def test_default_threshold_and_cooldown() -> None:
    """デフォルト値が正しい。"""
    assert DEFAULT_ESCALATION_THRESHOLD == 5
    assert DEFAULT_COOLDOWN_MINUTES == 30
