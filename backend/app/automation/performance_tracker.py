# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel


class PerformanceSummary(BaseModel):
    period_days: int
    total_proposals: Decimal
    executed_count: Decimal
    positive_count: Decimal
    total_gain_usd: Decimal
    total_gain_jpy: Decimal
    win_rate: Decimal


class PerformanceTracker:
    """過去実績の集計トラッカー。DB依存は Session 引数で注入。"""

    JPY_RATE: Decimal = Decimal("150")  # 1 USD = 150 JPY (固定レート)

    def get_summary(self, session: object, period_days: int = 30) -> PerformanceSummary:  # noqa: ARG002
        """本番実装: SQLAlchemy Session から集計。現在はモックにフォールバック。"""
        return self.get_summary_mock(period_days)

    def get_summary_mock(self, period_days: int = 30) -> PerformanceSummary:
        """テスト用モックデータ。"""
        total_proposals = Decimal("7")
        executed_count = Decimal("7")
        positive_count = Decimal("6")
        total_gain_usd = Decimal("42.50")
        total_gain_jpy = (total_gain_usd * self.JPY_RATE).quantize(Decimal("1"))
        win_rate = self._calc_win_rate(positive_count, executed_count)
        return PerformanceSummary(
            period_days=period_days,
            total_proposals=total_proposals,
            executed_count=executed_count,
            positive_count=positive_count,
            total_gain_usd=total_gain_usd,
            total_gain_jpy=total_gain_jpy,
            win_rate=win_rate,
        )

    def format_summary_ja(self, summary: PerformanceSummary) -> str:
        """日本語サマリー文を返す。"""
        total = int(summary.total_proposals)
        positive = int(summary.positive_count)
        gain_jpy = int(summary.total_gain_jpy)
        days = summary.period_days

        period_label = f"この{days}日間" if days != 30 else "この1ヶ月"

        if total == 0:
            return f"{period_label}でAIは提案がありませんでした。"

        sign = "+" if gain_jpy >= 0 else ""
        return (
            f"{period_label}でAIは{total}回提案、{positive}回でプラス。"
            f"全て従った場合{sign}￥{gain_jpy:,}"
        )

    # ── private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_win_rate(positive_count: Decimal, executed_count: Decimal) -> Decimal:
        try:
            if executed_count == Decimal("0"):
                return Decimal("0")
            return (positive_count / executed_count).quantize(Decimal("0.0001"))
        except InvalidOperation:
            return Decimal("0")
