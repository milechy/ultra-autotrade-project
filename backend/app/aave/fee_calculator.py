# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/fee_calculator.py

"""
AUM ベースの手数料計算モジュール。

- ManagementFee: AUM × 年率 0.5% の日割り計算
- PerformanceFee: 利益 × 10%
- MonthlyFeeSummary: 月次まとめ
"""

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, field_serializer


class ManagementFeeResult(BaseModel):
    """管理手数料の計算結果。"""

    fee_usd: Decimal
    aum_usd: Decimal
    rate: Decimal
    days: int
    below_minimum: bool

    @field_serializer("fee_usd", "aum_usd", "rate")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class PerformanceFeeResult(BaseModel):
    """パフォーマンス手数料の計算結果。"""

    fee_usd: Decimal
    profit_usd: Decimal
    rate: Decimal

    @field_serializer("fee_usd", "profit_usd", "rate")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class MonthlyFeeSummary(BaseModel):
    """月次手数料サマリー。"""

    management_fee: ManagementFeeResult
    performance_fee: PerformanceFeeResult
    total_fee: Decimal
    avg_aum: Decimal
    profit: Decimal
    period_days: int

    @field_serializer("total_fee", "avg_aum", "profit")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class FeeCalculator:
    """AUM ベースの手数料計算クラス。"""

    MANAGEMENT_FEE_ANNUAL_RATE: Decimal = Decimal("0.005")
    PERFORMANCE_FEE_RATE: Decimal = Decimal("0.10")
    MIN_AUM_USD: Decimal = Decimal("3000")

    def calculate_management_fee(
        self,
        aum_usd: Decimal,
        days: int = 1,
    ) -> ManagementFeeResult:
        """
        管理手数料を計算する。

        :param aum_usd: 運用資産額（USD）
        :param days: 計算対象日数（デフォルト 1 日）
        :return: ManagementFeeResult
        """
        daily_fee = aum_usd * self.MANAGEMENT_FEE_ANNUAL_RATE / Decimal("365")
        fee = daily_fee * Decimal(days)
        fee = fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        below_minimum = aum_usd < self.MIN_AUM_USD

        return ManagementFeeResult(
            fee_usd=fee,
            aum_usd=aum_usd,
            rate=self.MANAGEMENT_FEE_ANNUAL_RATE,
            days=days,
            below_minimum=below_minimum,
        )

    def calculate_performance_fee(
        self,
        profit_usd: Decimal,
    ) -> PerformanceFeeResult:
        """
        パフォーマンス手数料を計算する。

        :param profit_usd: 利益額（USD）。0 以下の場合は手数料なし。
        :return: PerformanceFeeResult
        """
        if profit_usd <= Decimal("0"):
            fee = Decimal("0.00")
        else:
            fee = profit_usd * self.PERFORMANCE_FEE_RATE
            fee = fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return PerformanceFeeResult(
            fee_usd=fee,
            profit_usd=profit_usd,
            rate=self.PERFORMANCE_FEE_RATE,
        )

    def calculate_monthly_summary(
        self,
        daily_aums: list[Decimal],
        monthly_profit: Decimal,
    ) -> MonthlyFeeSummary:
        """
        月次手数料サマリーを計算する。

        :param daily_aums: 各日の AUM（USD）リスト
        :param monthly_profit: 月間利益（USD）
        :return: MonthlyFeeSummary
        """
        avg_aum = sum(daily_aums) / Decimal(len(daily_aums))
        period_days = len(daily_aums)

        management_fee = self.calculate_management_fee(avg_aum, days=period_days)
        performance_fee = self.calculate_performance_fee(monthly_profit)
        total_fee = management_fee.fee_usd + performance_fee.fee_usd

        return MonthlyFeeSummary(
            management_fee=management_fee,
            performance_fee=performance_fee,
            total_fee=total_fee,
            avg_aum=avg_aum,
            profit=monthly_profit,
            period_days=period_days,
        )
