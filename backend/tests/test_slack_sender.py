# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""SlackNotificationSender のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.notifications.schemas import (
    NotificationChannel,
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.slack_sender import SlackNotificationSender


def _make_message(
    severity: NotificationSeverity = NotificationSeverity.INFO,
) -> NotificationMessage:
    return NotificationMessage(
        channel=NotificationChannel.SLACK,
        severity=severity,
        title="Test Alert",
        body="Test body content",
    )


@patch("app.notifications.slack_sender.httpx.post")
def test_send_success(mock_post: MagicMock) -> None:
    """正常系: 200 レスポンスで send() が成功する。"""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    sender = SlackNotificationSender(webhook_url="https://hooks.slack.com/test/webhook")
    sender.send(_make_message())

    mock_post.assert_called_once_with(
        "https://hooks.slack.com/test/webhook",
        json=pytest.approx(mock_post.call_args.kwargs["json"]),
        timeout=10,
    )
    mock_post.assert_called_once()


@patch("app.notifications.slack_sender.httpx.post")
def test_send_http_error_does_not_raise(mock_post: MagicMock) -> None:
    """HTTP エラー時に例外を送出しない（fail-safe）。"""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=mock_response
    )
    mock_post.return_value = mock_response

    sender = SlackNotificationSender(webhook_url="https://hooks.slack.com/test/webhook")
    # 例外が発生しないことを確認
    sender.send(_make_message())


@patch(
    "app.notifications.slack_sender.httpx.post",
    side_effect=__import__("httpx").ConnectError("Connection refused"),
)
def test_send_network_error_does_not_raise(mock_post: MagicMock) -> None:
    """ネットワークエラー時に例外を送出しない（fail-safe）。"""
    sender = SlackNotificationSender(webhook_url="https://hooks.slack.com/test/webhook")
    # 例外が発生しないことを確認
    sender.send(_make_message())


def test_build_payload_info() -> None:
    """INFO severity のペイロードが正しい emoji と color を含む。"""
    sender = SlackNotificationSender(webhook_url="https://hooks.slack.com/test/webhook")
    message = _make_message(severity=NotificationSeverity.INFO)
    payload = sender._build_payload(message)

    attachments = payload["attachments"]
    assert len(attachments) == 1
    attachment = attachments[0]

    assert attachment["color"] == "#36a64f"
    blocks = attachment["blocks"]
    title_block_text = blocks[0]["text"]["text"]
    body_block_text = blocks[1]["text"]["text"]

    assert ":information_source:" in title_block_text
    assert "Test Alert" in title_block_text
    assert "Test body content" in body_block_text


def test_build_payload_emergency() -> None:
    """EMERGENCY severity のペイロードが正しい emoji と color を含む。"""
    sender = SlackNotificationSender(webhook_url="https://hooks.slack.com/test/webhook")
    message = _make_message(severity=NotificationSeverity.EMERGENCY)
    payload = sender._build_payload(message)

    attachments = payload["attachments"]
    assert len(attachments) == 1
    attachment = attachments[0]

    assert attachment["color"] == "#b71c1c"
    blocks = attachment["blocks"]
    title_block_text = blocks[0]["text"]["text"]

    assert ":sos:" in title_block_text
    assert "Test Alert" in title_block_text


@patch("app.notifications.slack_sender.httpx.post")
def test_webhook_url_not_logged(mock_post: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    """Webhook URL がログに出力されない（セキュリティ）。"""
    import logging

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    webhook_url = "https://hooks.slack.com/secret/xxx"
    sender = SlackNotificationSender(webhook_url=webhook_url)

    with caplog.at_level(logging.DEBUG, logger="app.notifications.slack_sender"):
        sender.send(_make_message())

    for record in caplog.records:
        assert webhook_url not in record.getMessage(), (
            f"Webhook URL leaked in log: {record.getMessage()}"
        )