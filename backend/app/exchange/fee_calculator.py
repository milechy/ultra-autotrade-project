# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
手数料計算ロジック。

- TradingFeeCalculator: 取引手数料（maker/taker）の計算
- PerformanceFeeCalculator: ハイウォーターマーク方式のパフォーマンス費計算
"""

from decimal import Decimal


class TradingFeeCalculator:
    """
    maker/taker 手数料計算器。

    - maker_rate: Decimal (e.g. Decimal("0.001") = 0.1%)
    - taker_rate: Decimal (e.g. Decimal("0.001") = 0.1%)
    """

    def __init__(
        self,
        maker_rate: Decimal = Decimal("0.001"),
        taker_rate: Decimal = Decimal("0.001"),
    ) -> None:
        self._maker_rate = maker_rate
        self._taker_rate = taker_rate

    def calculate_maker_fee(self, amount_usd: Decimal) -> Decimal:
        """maker 手数料を計算する。"""
        return amount_usd * self._maker_rate

    def calculate_taker_fee(self, amount_usd: Decimal) -> Decimal:
        """taker 手数料を計算する。"""
        return amount_usd * self._taker_rate

    def calculate_round_trip_fee(self, amount_usd: Decimal) -> Decimal:
        """往復手数料（エントリー + エグジット）を計算する。maker + taker の合計 x2。"""
        return (self._maker_rate + self._taker_rate) * amount_usd * Decimal("2")


class PerformanceFeeCalculator:
    """
    ハイウォーターマーク方式パフォーマンス費計算器。

    - fee_rate: パフォーマンス費率 (e.g. Decimal("0.20") = 20%)
    - hwm: ハイウォーターマーク (現在の最高純資産額)
    """

    def __init__(
        self,
        fee_rate: Decimal = Decimal("0.20"),
        initial_hwm: Decimal = Decimal("0"),
    ) -> None:
        self._fee_rate = fee_rate
        self._hwm = initial_hwm

    def calculate_performance_fee(self, current_nav: Decimal) -> Decimal:
        """
        現在のNAVに対するパフォーマンス費を計算する。
        - current_nav > hwm の場合: fee = (current_nav - hwm) * fee_rate
        - current_nav <= hwm の場合: fee = 0 (HWMを下回っている → 費用なし)
        - 計算後にHWMを更新しない（update_hwm()を明示的に呼ぶ）
        """
        if current_nav > self._hwm:
            return (current_nav - self._hwm) * self._fee_rate
        return Decimal("0")

    def update_hwm(self, current_nav: Decimal) -> None:
        """HWMを current_nav で更新する（current_nav > hwm の場合のみ）。"""
        if current_nav > self._hwm:
            self._hwm = current_nav

    @property
    def hwm(self) -> Decimal:
        """現在のHWM値を返す。"""
        return self._hwm
