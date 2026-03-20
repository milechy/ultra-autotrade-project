# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from __future__ import annotations

from decimal import Decimal

from app.automation.performance_tracker import (
    PerformanceSummary,
    PerformanceTracker,
)

tracker = PerformanceTracker()


def test_summary_mock() -> None:
    summary = tracker.get_summary_mock(period_days=30)
    assert summary.total_proposals == Decimal("7")
    assert summary.executed_count == Decimal("7")
    assert summary.positive_count == Decimal("6")
    assert summary.win_rate == Decimal("0.8571")


def test_format_ja() -> None:
    summary = tracker.get_summary_mock(period_days=30)
    text = tracker.format_summary_ja(summary)
    assert "AIは7回提案" in text
    assert "6回でプラス" in text


def test_zero_proposals() -> None:
    summary = PerformanceSummary(
        period_days=30,
        total_proposals=Decimal("0"),
        executed_count=Decimal("0"),
        positive_count=Decimal("0"),
        total_gain_usd=Decimal("0"),
        total_gain_jpy=Decimal("0"),
        win_rate=Decimal("0"),
    )
    text = tracker.format_summary_ja(summary)
    assert "提案がありません" in text
    assert summary.win_rate == Decimal("0")


def test_all_decimal() -> None:
    summary = tracker.get_summary_mock()
    assert isinstance(summary.total_proposals, Decimal)
    assert isinstance(summary.executed_count, Decimal)
    assert isinstance(summary.positive_count, Decimal)
    assert isinstance(summary.total_gain_usd, Decimal)
    assert isinstance(summary.total_gain_jpy, Decimal)
    assert isinstance(summary.win_rate, Decimal)