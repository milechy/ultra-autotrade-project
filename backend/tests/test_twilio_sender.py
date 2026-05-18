# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""TwilioSender のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.notifications.schemas import (
    NotificationChannel,
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.twilio_sender import TwilioSender, _escape_xml


def _make_sender(**kwargs: object) -> TwilioSender:
    defaults = {
        "account_sid": "ACtest123",
        "auth_token": "secret_token",
        "from_number": "+15550001111",
        "to_number": "+819000000000",
        "oncall_start_hour": 9,
        "oncall_end_hour": 22,
    }
    defaults.update(kwargs)
    return TwilioSender(**defaults)  # type: ignore[arg-type]


def _make_message(
    severity: NotificationSeverity = NotificationSeverity.EMERGENCY,
) -> NotificationMessage:
    return NotificationMessage(
        channel=NotificationChannel.PHONE,
        severity=severity,
        title="HF 緊急アラート",
        body="Health Factor が 1.3 に低下しました。",
    )


# ---- オンコール時間内テスト ----


@patch("app.notifications.twilio_sender.httpx.post")
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=True)
def test_send_emergency_oncall_hours_calls_voice(
    mock_hours: MagicMock, mock_post: MagicMock
) -> None:
    """オンコール時間内の EMERGENCY は音声電話を試みる。"""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"sid": "CA12345678abcdefgh"}
    mock_post.return_value = mock_response

    sender = _make_sender()
    sender.send(_make_message(NotificationSeverity.EMERGENCY))

    assert mock_post.called
    call_kwargs = mock_post.call_args
    assert "Calls.json" in call_kwargs.args[0]


@patch("app.notifications.twilio_sender.httpx.post")
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=True)
def test_send_alert_oncall_hours_calls_voice(mock_hours: MagicMock, mock_post: MagicMock) -> None:
    """オンコール時間内の ALERT も音声電話を試みる。"""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"sid": "CA99999"}
    mock_post.return_value = mock_response

    sender = _make_sender()
    sender.send(_make_message(NotificationSeverity.ALERT))

    assert mock_post.called


@patch("app.notifications.twilio_sender.httpx.post")
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=True)
def test_voice_failure_falls_back_to_sms(mock_hours: MagicMock, mock_post: MagicMock) -> None:
    """音声電話失敗時は SMS にフォールバックする。"""
    import httpx

    voice_response = MagicMock()
    voice_response.status_code = 500
    voice_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=voice_response
    )
    sms_response = MagicMock()
    sms_response.raise_for_status.return_value = None
    sms_response.json.return_value = {"sid": "SM11111"}

    mock_post.side_effect = [voice_response, sms_response]

    sender = _make_sender()
    sender.send(_make_message())

    assert mock_post.call_count == 2
    sms_url = mock_post.call_args_list[1].args[0]
    assert "Messages.json" in sms_url


# ---- オンコール時間外テスト ----


@patch("app.notifications.twilio_sender.httpx.post")
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=False)
def test_send_emergency_off_hours_sends_sms_only(
    mock_hours: MagicMock, mock_post: MagicMock
) -> None:
    """オンコール時間外の EMERGENCY は SMS のみ送信する。"""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"sid": "SM22222"}
    mock_post.return_value = mock_response

    sender = _make_sender()
    sender.send(_make_message())

    assert mock_post.call_count == 1
    url = mock_post.call_args.args[0]
    assert "Messages.json" in url


# ---- 重要度フィルタリングテスト ----


@patch("app.notifications.twilio_sender.httpx.post")
def test_send_info_does_not_call_twilio(mock_post: MagicMock) -> None:
    """INFO は電話/SMS の対象外。"""
    sender = _make_sender()
    sender.send(_make_message(NotificationSeverity.INFO))
    mock_post.assert_not_called()


@patch("app.notifications.twilio_sender.httpx.post")
def test_send_warning_does_not_call_twilio(mock_post: MagicMock) -> None:
    """WARNING は電話/SMS の対象外。"""
    sender = _make_sender()
    sender.send(_make_message(NotificationSeverity.WARNING))
    mock_post.assert_not_called()


# ---- fail-safe テスト ----


@patch("app.notifications.twilio_sender.httpx.post", side_effect=Exception("Network error"))
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=True)
def test_send_does_not_raise_on_exception(mock_hours: MagicMock, mock_post: MagicMock) -> None:
    """例外発生時も send() は例外を送出しない（fail-safe）。"""
    sender = _make_sender()
    sender.send(_make_message())  # raises しないこと


# ---- セキュリティテスト ----


@patch("app.notifications.twilio_sender.httpx.post")
@patch("app.notifications.twilio_sender.TwilioSender._is_oncall_hours", return_value=True)
def test_auth_token_not_in_log(
    mock_hours: MagicMock, mock_post: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Auth Token がログに出力されない。"""
    import logging

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"sid": "CA99999"}
    mock_post.return_value = mock_response

    sender = _make_sender(auth_token="super_secret_token_xyz")
    with caplog.at_level(logging.DEBUG, logger="app.notifications.twilio_sender"):
        sender.send(_make_message())

    for record in caplog.records:
        assert "super_secret_token_xyz" not in record.getMessage()


# ---- XML エスケープテスト ----


def test_escape_xml_ampersand() -> None:
    assert _escape_xml("A&B") == "A&amp;B"


def test_escape_xml_lt_gt() -> None:
    assert _escape_xml("<tag>") == "&lt;tag&gt;"


def test_escape_xml_no_change() -> None:
    assert _escape_xml("normal text") == "normal text"


# ---- オンコール時間判定テスト ----


def test_is_oncall_hours_within_range() -> None:
    """9:00-21:59 JST はオンコール時間内。"""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    JST = ZoneInfo("Asia/Tokyo")
    # 14:00 JST
    ts = datetime(2026, 5, 18, 14, 0, tzinfo=JST).astimezone(timezone.utc)

    with patch("app.notifications.twilio_sender.datetime") as mock_dt:
        mock_dt.now.return_value = ts
        sender = _make_sender()
        assert sender._is_oncall_hours() is True


def test_is_oncall_hours_outside_range() -> None:
    """23:00 JST はオンコール時間外。"""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    JST = ZoneInfo("Asia/Tokyo")
    ts = datetime(2026, 5, 18, 23, 0, tzinfo=JST).astimezone(timezone.utc)

    with patch("app.notifications.twilio_sender.datetime") as mock_dt:
        mock_dt.now.return_value = ts
        sender = _make_sender()
        assert sender._is_oncall_hours() is False
