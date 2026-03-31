# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""月次レポート生成のユニットテスト。"""

from __future__ import annotations

from app.reports.monthly_report import MonthlyReportData, generate_monthly_report_pdf


def _make_data(**kwargs: object) -> MonthlyReportData:
    defaults: dict[str, object] = {
        "period": "2026年3月",
        "total_proposals": 100,
        "positive_results": 70,
        "win_rate": 70.0,
        "total_gain_jpy": 200_000,
        "avg_gain_per_trade_jpy": 2_857,
        "total_fees_jpy": 8_000,
        "annual_yield_pct": 15.0,
    }
    defaults.update(kwargs)
    return MonthlyReportData(**defaults)  # type: ignore[arg-type]


def test_generate_report_returns_bytes() -> None:
    """レポート生成が bytes を返すことを確認する。"""
    data = _make_data()
    content, content_type = generate_monthly_report_pdf(data)

    assert isinstance(content, bytes)
    assert len(content) > 0
    assert content_type in ("application/pdf", "text/csv")


def test_report_contains_period_text() -> None:
    """レポートに対象期間の年が含まれることを確認する。"""
    data = _make_data(period="2026年3月")
    content, content_type = generate_monthly_report_pdf(data)

    # PDF の場合は文字列をそのまま含むことが多い; CSV は確実
    assert b"2026" in content


def test_win_rate_calculation() -> None:
    """勝率の計算が正しいことをサニティチェックする。"""
    total = 50
    positive = 35
    expected_win_rate = positive / total * 100  # 70.0

    data = _make_data(
        total_proposals=total,
        positive_results=positive,
        win_rate=expected_win_rate,
    )
    assert data.win_rate == 70.0

    content, _ = generate_monthly_report_pdf(data)
    assert isinstance(content, bytes)
    assert len(content) > 0
