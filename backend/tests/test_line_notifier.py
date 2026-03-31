# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""LINE Notify クライアントのユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.notifications.line_notifier import (
    HF_HARD_STOP_THRESHOLD,
    HF_WARNING_THRESHOLD,
    LINENotifyClient,
    notify_health_factor,
)
from app.notifications.schemas import NotificationChannel, NotificationMessage, NotificationSeverity

# ── LINENotifyClient.send() ───────────────────────────────────────────────────


def _make_message(severity: NotificationSeverity) -> NotificationMessage:
    return NotificationMessage(
        channel=NotificationChannel.LINE,
        severity=severity,
        title="テストタイトル",
        body="テスト本文",
    )


def test_send_skips_when_no_token(caplog: pytest.LogCaptureFixture) -> None:
    """トークン未設定時はスキップしてログに警告を出す。"""
    client = LINENotifyClient(token="")
    with caplog.at_level("WARNING"):
        client.send(_make_message(NotificationSeverity.WARNING))
    assert any("LINE_NOTIFY_TOKEN" in r.message for r in caplog.records)


def test_send_skips_below_min_severity() -> None:
    """min_severity 未満のメッセージは送信しない。"""
    client = LINENotifyClient(token="dummy_token", min_severity=NotificationSeverity.WARNING)
    with patch("httpx.post") as mock_post:
        client.send(_make_message(NotificationSeverity.INFO))
        mock_post.assert_not_called()


def test_send_calls_line_api_for_warning() -> None:
    """WARNING メッセージが LINE Notify API に送信される。"""
    client = LINENotifyClient(token="dummy_token", min_severity=NotificationSeverity.WARNING)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        client.send(_make_message(NotificationSeverity.WARNING))
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "https://notify-api.line.me/api/notify"
        assert "Bearer dummy_token" in call_kwargs[1]["headers"]["Authorization"]


def test_send_calls_line_api_for_emergency() -> None:
    """EMERGENCY メッセージが LINE Notify API に送信される。"""
    client = LINENotifyClient(token="dummy_token", min_severity=NotificationSeverity.WARNING)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        client.send(_make_message(NotificationSeverity.EMERGENCY))
        mock_post.assert_called_once()


def test_send_handles_http_error_without_raising(caplog: pytest.LogCaptureFixture) -> None:
    """HTTP エラー時も例外を投げずにログに記録する。"""
    import httpx

    client = LINENotifyClient(token="dummy_token")
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch(
        "httpx.post",
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        ),
    ):
        with caplog.at_level("ERROR"):
            client.send(_make_message(NotificationSeverity.WARNING))
    assert any("LINE Notify 送信失敗" in r.message for r in caplog.records)


def test_send_handles_generic_error_without_raising(caplog: pytest.LogCaptureFixture) -> None:
    """ネットワーク障害時も例外を投げずにログに記録する。"""
    client = LINENotifyClient(token="dummy_token")

    with patch("httpx.post", side_effect=ConnectionError("network error")):
        with caplog.at_level("ERROR"):
            client.send(_make_message(NotificationSeverity.WARNING))
    assert any("LINE Notify 送信失敗" in r.message for r in caplog.records)


def test_format_message_includes_severity_and_title() -> None:
    """フォーマットされたメッセージに severity と title が含まれる。"""
    client = LINENotifyClient(token="dummy_token")
    msg = _make_message(NotificationSeverity.WARNING)
    formatted = client._format_message(msg)
    assert "WARNING" in formatted
    assert "テストタイトル" in formatted
    assert "テスト本文" in formatted


# ── notify_health_factor() ─────────────────────────────────────────────────────


def test_notify_hf_below_hard_stop_sends_emergency() -> None:
    """HF が HARD_STOP 閾値未満の場合 EMERGENCY 通知が送られる。"""
    hf = HF_HARD_STOP_THRESHOLD - Decimal("0.01")  # 1.59
    with patch("app.notifications.line_notifier.LINENotifyClient.send") as mock_send:
        notify_health_factor(hf, token="dummy_token")
        mock_send.assert_called_once()
        msg: NotificationMessage = mock_send.call_args[0][0]
        assert msg.severity == NotificationSeverity.EMERGENCY
        assert "HARD_STOP" in msg.title


def test_notify_hf_below_warning_sends_warning() -> None:
    """HF が WARNING 閾値未満・HARD_STOP 閾値以上の場合 WARNING 通知が送られる。"""
    hf = HF_WARNING_THRESHOLD - Decimal("0.01")  # 1.79
    with patch("app.notifications.line_notifier.LINENotifyClient.send") as mock_send:
        notify_health_factor(hf, token="dummy_token")
        mock_send.assert_called_once()
        msg: NotificationMessage = mock_send.call_args[0][0]
        assert msg.severity == NotificationSeverity.WARNING
        assert "WARNING" in msg.title


def test_notify_hf_above_warning_does_not_send() -> None:
    """HF が WARNING 閾値以上の場合は通知しない。"""
    hf = HF_WARNING_THRESHOLD  # 1.8 (exactly at threshold, not below)
    with patch("app.notifications.line_notifier.LINENotifyClient.send") as mock_send:
        notify_health_factor(hf, token="dummy_token")
        mock_send.assert_not_called()


def test_notify_hf_safe_level_does_not_send() -> None:
    """HF が安全域（2.5）の場合は通知しない。"""
    hf = Decimal("2.5")
    with patch("app.notifications.line_notifier.LINENotifyClient.send") as mock_send:
        notify_health_factor(hf, token="dummy_token")
        mock_send.assert_not_called()


def test_notify_hf_uses_env_token_when_none_given() -> None:
    """token=None の場合は環境変数 LINE_NOTIFY_TOKEN を使用する。"""
    hf = HF_HARD_STOP_THRESHOLD - Decimal("0.1")
    with patch.dict("os.environ", {"LINE_NOTIFY_TOKEN": "env_token"}):
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response
            notify_health_factor(hf)
            mock_post.assert_called_once()
            assert "Bearer env_token" in mock_post.call_args[1]["headers"]["Authorization"]
