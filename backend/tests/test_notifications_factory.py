# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_notifications_factory.py
"""
get_notification_service() ファクトリの構成テスト。

LINE_MIN_SEVERITY env を LINENotificationSender に伝播することを担保し、
AI proposal (severity=warning) を本番で LINE 配信するための opt-in
パスがコード側で完成していることを検証する。

実通知送信はしない (httpx も触らない)。
"""

from __future__ import annotations

import os
from unittest.mock import patch

from app.notifications import config as notif_config
from app.notifications.factory import (
    get_notification_service,
    reset_notification_service,
)
from app.notifications.line_sender import LINENotificationSender
from app.notifications.schemas import NotificationSeverity


def _clean_env_patch() -> dict[str, str]:
    """テストで触る通知系 env 以外はそのまま継承する辞書を返す。"""
    return {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "LINE_NOTIFY_TOKEN",
            "SLACK_WEBHOOK_URL",
            "NOTIFICATION_CHANNEL",
            "LINE_CHANNEL_ACCESS_TOKEN",
            "LINE_USER_ID",
            "LINE_MIN_SEVERITY",
        }
    }


def _reset() -> None:
    """サービスと設定のシングルトンキャッシュをリセット。"""
    reset_notification_service()
    notif_config.reset_notification_settings()


class TestFactoryLineMinSeverityPropagation:
    """LINE Messaging API 設定済みのとき、LINE_MIN_SEVERITY が伝播するか。"""

    def _line_sender_from_service(self) -> LINENotificationSender | None:
        svc = get_notification_service()
        for sender in svc._senders:  # noqa: SLF001 - test inspection
            if isinstance(sender, LINENotificationSender):
                return sender
        return None

    def test_default_min_severity_is_alert(self) -> None:
        """LINE_MIN_SEVERITY 未指定なら既定 ALERT を維持。"""
        env = _clean_env_patch()
        env["LINE_CHANNEL_ACCESS_TOKEN"] = "dummy_channel_token"
        env["LINE_USER_ID"] = "U_dummy"
        with patch.dict(os.environ, env, clear=True):
            _reset()
            try:
                ls = self._line_sender_from_service()
                assert ls is not None, "LINE sender should be configured"
                assert ls._min_severity == NotificationSeverity.ALERT  # noqa: SLF001
            finally:
                _reset()

    def test_warning_opt_in_propagates(self) -> None:
        """LINE_MIN_SEVERITY=warning なら LINE sender も WARNING になる。"""
        env = _clean_env_patch()
        env["LINE_CHANNEL_ACCESS_TOKEN"] = "dummy_channel_token"
        env["LINE_USER_ID"] = "U_dummy"
        env["LINE_MIN_SEVERITY"] = "warning"
        with patch.dict(os.environ, env, clear=True):
            _reset()
            try:
                ls = self._line_sender_from_service()
                assert ls is not None
                assert ls._min_severity == NotificationSeverity.WARNING  # noqa: SLF001
            finally:
                _reset()

    def test_no_line_sender_when_not_configured(self) -> None:
        """LINE Messaging 未設定 (token / user_id なし) なら LINE sender は構成されない。"""
        env = _clean_env_patch()
        with patch.dict(os.environ, env, clear=True):
            _reset()
            try:
                ls = self._line_sender_from_service()
                assert ls is None
            finally:
                _reset()


class TestFactoryNoSlackWhenWebhookUnset:
    """SLACK_WEBHOOK_URL 未設定環境では Slack sender が組み込まれない。"""

    def test_no_slack_sender_means_no_implicit_send(self) -> None:
        from app.notifications.escalation import SlackEscalationSender
        from app.notifications.slack_sender import SlackNotificationSender

        env = _clean_env_patch()
        with patch.dict(os.environ, env, clear=True):
            _reset()
            try:
                svc = get_notification_service()
                assert not any(
                    isinstance(s, (SlackEscalationSender, SlackNotificationSender))
                    for s in svc._senders  # noqa: SLF001
                )
            finally:
                _reset()


class TestLineSenderSeverityGatingForProposalLevel:
    """ai_proposal_notification (severity=warning) と LINE sender の gating。"""

    def test_proposal_warning_dropped_when_min_alert(self) -> None:
        from app.notifications.templates import ai_proposal_notification

        sender = LINENotificationSender(
            channel_access_token="dummy_token",
            user_id="U_dummy",
            min_severity=NotificationSeverity.ALERT,
        )
        payload = ai_proposal_notification(
            operation="BUY",
            asset="USDC",
            amount=100,  # type: ignore[arg-type]
            confidence=70,
        )
        with patch("httpx.post") as mock_post:
            sender.send(payload.notification_message)
            mock_post.assert_not_called()

    def test_proposal_warning_delivered_when_min_warning(self) -> None:
        from unittest.mock import MagicMock

        from app.notifications.templates import ai_proposal_notification

        sender = LINENotificationSender(
            channel_access_token="dummy_token",
            user_id="U_dummy",
            min_severity=NotificationSeverity.WARNING,
        )
        payload = ai_proposal_notification(
            operation="BUY",
            asset="USDC",
            amount=100,  # type: ignore[arg-type]
            confidence=70,
        )
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_response) as mock_post:
            sender.send(payload.notification_message)
            mock_post.assert_called_once()
