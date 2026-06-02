# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""LINE Messaging API Flex Message のユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.notifications.line_messaging import (
    LINEFlexMessageSender,
    build_alert_flex_bubble,
    build_monthly_report_flex_bubble,
)
from app.automation.scheduled_tasks import _extract_line_user_id


# ── build_monthly_report_flex_bubble ──────────────────────────────────────────


def test_monthly_report_flex_bubble_structure() -> None:
    """Flex Message が正しい構造を持つことを確認する。"""
    msg = build_monthly_report_flex_bubble(
        period="2026年5月",
        net_profit_jpy=Decimal("12345"),
        fee_amount_jpy=Decimal("500"),
        win_rate=72.5,
        total_proposals=40,
    )
    assert msg["type"] == "flex"
    assert "2026年5月" in msg["altText"]
    bubble = msg["contents"]
    assert bubble["type"] == "bubble"
    assert bubble["header"]["contents"][1]["text"] == "2026年5月"


def test_monthly_report_flex_bubble_positive_profit_color() -> None:
    """利益がプラスのとき緑色が使用される。"""
    msg = build_monthly_report_flex_bubble(
        period="2026年5月",
        net_profit_jpy=Decimal("5000"),
        fee_amount_jpy=Decimal("100"),
        win_rate=60.0,
        total_proposals=10,
    )
    profit_row = msg["contents"]["body"]["contents"][0]
    profit_text = profit_row["contents"][1]
    assert profit_text["color"] == "#00B900"
    assert profit_text["text"].startswith("+")


def test_monthly_report_flex_bubble_negative_profit_color() -> None:
    """損失のとき赤色が使用される。"""
    msg = build_monthly_report_flex_bubble(
        period="2026年5月",
        net_profit_jpy=Decimal("-3000"),
        fee_amount_jpy=Decimal("200"),
        win_rate=30.0,
        total_proposals=10,
    )
    profit_row = msg["contents"]["body"]["contents"][0]
    profit_text = profit_row["contents"][1]
    assert profit_text["color"] == "#FF0000"
    assert "-" in profit_text["text"]


def test_monthly_report_flex_bubble_zero_proposals() -> None:
    """提案0件でも例外なく生成できる。"""
    msg = build_monthly_report_flex_bubble(
        period="2026年5月",
        net_profit_jpy=Decimal("0"),
        fee_amount_jpy=Decimal("0"),
        win_rate=0.0,
        total_proposals=0,
    )
    assert msg["type"] == "flex"


# ── _extract_line_user_id ─────────────────────────────────────────────────────


def test_extract_line_user_id_valid() -> None:
    """LINE 認証ユーザーのメールから user_id を抽出できる。"""
    assert _extract_line_user_id("line_Uabcdef1234567890@line.local") == "Uabcdef1234567890"


def test_extract_line_user_id_short_id() -> None:
    """短い LINE user_id でも抽出できる。"""
    assert _extract_line_user_id("line_Uabc@line.local") == "Uabc"


def test_extract_line_user_id_non_line_email() -> None:
    """LINE 以外のメールは None を返す。"""
    assert _extract_line_user_id("user@example.com") is None
    assert _extract_line_user_id("admin@ultra-auto-trade.com") is None


def test_extract_line_user_id_privy_email() -> None:
    """Privy 認証のメールは None を返す。"""
    assert _extract_line_user_id("privy_abc123@privy.io") is None


# ── LINEFlexMessageSender.send_flex ──────────────────────────────────────────


def test_send_flex_success() -> None:
    """send_flex が成功したとき True を返す。"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch("app.notifications.line_messaging.httpx.post", return_value=mock_resp):
        sender = LINEFlexMessageSender(
            channel_access_token="test_token",
            user_id="Utest",
        )
        result = sender.send_flex("タイトル", "本文", "info")

    assert result is True


def test_send_flex_http_error() -> None:
    """HTTP エラー時に False を返す（例外を握りつぶさない）。"""
    import httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=mock_resp
    )

    with patch("app.notifications.line_messaging.httpx.post", return_value=mock_resp):
        sender = LINEFlexMessageSender(
            channel_access_token="bad_token",
            user_id="Utest",
        )
        result = sender.send_flex("タイトル", "本文", "emergency")

    assert result is False


# ── UserSettings.line_monthly_opt_in ─────────────────────────────────────────


def test_user_model_has_line_monthly_opt_in() -> None:
    """User モデルに line_monthly_opt_in カラムが定義されている。"""
    from app.auth.models import User
    from sqlalchemy import inspect

    mapper = inspect(User)
    col_names = [c.key for c in mapper.mapper.column_attrs]
    assert "line_monthly_opt_in" in col_names


def test_user_model_line_monthly_opt_in_can_be_set() -> None:
    """line_monthly_opt_in を True に設定できる。"""
    from app.auth.models import User

    user = User(
        email="line_Utest2@line.local",
        username="line_Utest2",
        hashed_password="x",
        line_monthly_opt_in=True,
    )
    assert user.line_monthly_opt_in is True
