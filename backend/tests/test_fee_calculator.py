# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_fee_calculator.py

"""
FeeCalculator のユニットテスト。

- ManagementFeeResult / PerformanceFeeResult の計算精度を検証
- MonthlyFeeSummary の合計計算を検証
- fee_router の /api/fees/schedule エンドポイントを検証
"""

from decimal import Decimal

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.aave.fee_calculator import FeeCalculator
from app.aave.fee_router import router as fee_router


class TestFeeCalculator:
    def test_management_fee_daily(self) -> None:
        """AUM=10000, days=1 → fee_usd == 0.14"""
        result = FeeCalculator().calculate_management_fee(Decimal("10000"), 1)
        assert result.fee_usd == Decimal("0.14")

    def test_management_fee_monthly(self) -> None:
        """AUM=10000, days=30 → fee_usd == 4.11"""
        result = FeeCalculator().calculate_management_fee(Decimal("10000"), 30)
        assert result.fee_usd == Decimal("4.11")

    def test_performance_fee_profit(self) -> None:
        """profit=100 → fee_usd == 10.00"""
        result = FeeCalculator().calculate_performance_fee(Decimal("100"))
        assert result.fee_usd == Decimal("10.00")

    def test_performance_fee_no_profit(self) -> None:
        """profit=0 → fee_usd == 0.00"""
        result = FeeCalculator().calculate_performance_fee(Decimal("0"))
        assert result.fee_usd == Decimal("0.00")

    def test_performance_fee_loss(self) -> None:
        """profit=-50 → fee_usd == 0.00"""
        result = FeeCalculator().calculate_performance_fee(Decimal("-50"))
        assert result.fee_usd == Decimal("0.00")

    def test_monthly_summary(self) -> None:
        """daily_aums=[10000]*30, profit=500 → total_fee == 54.11"""
        daily_aums = [Decimal("10000")] * 30
        summary = FeeCalculator().calculate_monthly_summary(daily_aums, Decimal("500"))
        expected_total = Decimal("4.11") + Decimal("50.00")
        assert summary.total_fee == expected_total

    def test_below_minimum_warning(self) -> None:
        """AUM < 3000 → below_minimum True; AUM >= 3000 → False"""
        calc = FeeCalculator()
        result_below = calc.calculate_management_fee(Decimal("2000"), 1)
        assert result_below.below_minimum is True

        result_above = calc.calculate_management_fee(Decimal("5000"), 1)
        assert result_above.below_minimum is False

    def test_all_decimal(self) -> None:
        """ManagementFeeResult / PerformanceFeeResult の数値フィールドが全て Decimal"""
        calc = FeeCalculator()
        mgmt = calc.calculate_management_fee(Decimal("10000"), 30)
        assert isinstance(mgmt.fee_usd, Decimal)
        assert isinstance(mgmt.aum_usd, Decimal)
        assert isinstance(mgmt.rate, Decimal)

        perf = calc.calculate_performance_fee(Decimal("100"))
        assert isinstance(perf.fee_usd, Decimal)
        assert isinstance(perf.profit_usd, Decimal)
        assert isinstance(perf.rate, Decimal)

    def test_fee_schedule_endpoint(self) -> None:
        """GET /api/fees/schedule → 200 + management_fee_annual_rate キーを含む"""
        app = FastAPI()
        app.include_router(fee_router)
        client = TestClient(app)

        response = client.get("/api/fees/schedule")
        assert response.status_code == 200
        data = response.json()
        assert "management_fee_annual_rate" in data
