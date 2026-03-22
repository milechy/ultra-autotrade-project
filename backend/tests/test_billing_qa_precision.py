# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_billing_qa_precision.py
"""
Billing QA: Decimal 精度・丸めテスト

BillingService の全計算が Decimal のみを使用し、
ROUND_HALF_UP で正しく丸められることを検証する。
float との混合演算（float 汚染）がないことも確認する。
"""

from decimal import Decimal

import pytest

from app.billing.service import BillingService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> BillingService:
    """テスト対象の BillingService インスタンス。"""
    return BillingService()


# ---------------------------------------------------------------------------
# TestManagementFeeDecimalPrecision
# ---------------------------------------------------------------------------


class TestManagementFeeDecimalPrecision:
    """管理報酬の Decimal 精度テスト。"""

    def test_10000_aum_exact_6dp_value(self, svc: BillingService) -> None:
        """AUM=$10,000, rate=0.005 → 10000*0.005/365 = 0.136986...301 → 0.136986。

        7桁目が 3（< 5）なので切り捨て。
        """
        result = svc.calculate_daily_management_fee(
            aum=Decimal("10000"),
            rate=Decimal("0.005"),
        )
        # 10000 * 0.005 / 365 = 0.13698630136...  7桁目=3 → 切り捨て
        assert result == Decimal("0.136986")

    def test_3000_aum_7th_digit_8_rounds_up(self, svc: BillingService) -> None:
        """AUM=$3,000（最低額ちょうど）, rate=0.005 → 15/365 = 0.04109589... 7桁目=8 → 切り上げ。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("3000"),
            rate=Decimal("0.005"),
        )
        # 15/365 = 0.041095890...  7桁目=8 → ROUND_HALF_UP → 0.041096
        assert result == Decimal("0.041096")

    def test_large_aum_10M_no_overflow(self, svc: BillingService) -> None:
        """AUM=$10,000,000 での計算がオーバーフローせず正の Decimal 値を返すこと。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("10000000"),
            rate=Decimal("0.005"),
        )
        assert isinstance(result, Decimal)
        assert result > Decimal("0")
        # 10000000 * 0.005 / 365 ≈ 136.986...
        assert Decimal("136") < result < Decimal("138")

    def test_result_is_decimal_type(self, svc: BillingService) -> None:
        """戻り値が Decimal 型（float でない）であること。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("50000"),
            rate=Decimal("0.005"),
        )
        assert isinstance(result, Decimal)
        assert not isinstance(result, float)

    def test_result_has_6dp_max_precision(self, svc: BillingService) -> None:
        """結果の小数点以下が最大 6 桁であること（exponent >= -6）。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("12345"),
            rate=Decimal("0.005"),
        )
        _, _, exponent = result.as_tuple()
        assert exponent >= -6, f"Expected exponent >= -6, got {exponent}"


# ---------------------------------------------------------------------------
# TestPerformanceFeeDecimalPrecision
# ---------------------------------------------------------------------------


class TestPerformanceFeeDecimalPrecision:
    """成果報酬の Decimal 精度テスト。"""

    def test_profit_1234_567890_exact_value(self, svc: BillingService) -> None:
        """利益=$1,234.567890, rate=0.10 → 123.456789（6桁保持）。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("11234.567890"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        # profit = 1234.567890, fee = 1234.567890 * 0.10 = 123.4567890
        # 7桁目=0 → 切り捨て → 123.456789
        assert result == Decimal("123.456789")

    def test_result_is_decimal_type_on_profit(self, svc: BillingService) -> None:
        """利益ありケースの戻り値が Decimal 型（float でない）であること。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("11000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert isinstance(result, Decimal)
        assert not isinstance(result, float)

    def test_result_has_6dp_max_precision(self, svc: BillingService) -> None:
        """結果の小数点以下が最大 6 桁であること（exponent >= -6）。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("10001.23456789"),
            hwm=Decimal("10000"),
            rate=Decimal("0.20"),
        )
        _, _, exponent = result.as_tuple()
        assert exponent >= -6, f"Expected exponent >= -6, got {exponent}"

    def test_loss_returns_decimal_zero_not_int_or_float(self, svc: BillingService) -> None:
        """損失ケースで返る Decimal('0') が Decimal 型であること（int/float でないこと）。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("9000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert type(result) is Decimal
        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# TestRoundingHalfUp
# ---------------------------------------------------------------------------


class TestRoundingHalfUp:
    """ROUND_HALF_UP の適用を検証するテスト。"""

    def test_management_fee_7th_digit_3_rounds_down(self, svc: BillingService) -> None:
        """AUM=10000, rate=0.005 → 7桁目=3 → ROUND_HALF_UP で切り捨て → 0.136986。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("10000"),
            rate=Decimal("0.005"),
        )
        # 0.1369863013... 7桁目=3 → 切り捨て（ROUND_HALF_UP では 0.136986）
        assert result == Decimal("0.136986")

    def test_management_fee_7th_digit_8_rounds_up(self, svc: BillingService) -> None:
        """AUM=3000, rate=0.005 → 7桁目=8 → ROUND_HALF_UP で切り上げ → 0.041096。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("3000"),
            rate=Decimal("0.005"),
        )
        # 0.04109589... 7桁目=8 → 切り上げ
        assert result == Decimal("0.041096")

    def test_performance_fee_7th_digit_5_rounds_up(self, svc: BillingService) -> None:
        """7桁目がちょうど 5 の場合、ROUND_HALF_UP で切り上げられること。

        profit = 0.0000005, rate = 1 → 0.0000005
        quantize(0.000001, ROUND_HALF_UP): 0.5 × 10^-6 → 1 × 10^-6 = 0.000001
        """
        result = svc.calculate_performance_fee(
            current_value=Decimal("10000.0000005"),
            hwm=Decimal("10000"),
            rate=Decimal("1"),
        )
        assert result == Decimal("0.000001")


# ---------------------------------------------------------------------------
# TestFloatContamination
# ---------------------------------------------------------------------------


class TestFloatContamination:
    """float 汚染チェック: 全 public メソッドが Decimal のみを返すことを確認。"""

    def test_management_fee_result_type_is_decimal(self, svc: BillingService) -> None:
        """calculate_daily_management_fee の戻り値の型が正確に Decimal であること。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("100000"),
            rate=Decimal("0.005"),
        )
        assert type(result) is Decimal

    def test_performance_fee_profit_result_type_is_decimal(self, svc: BillingService) -> None:
        """calculate_performance_fee（利益あり）の戻り値の型が正確に Decimal であること。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("15000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert type(result) is Decimal

    def test_performance_fee_loss_result_type_is_decimal(self, svc: BillingService) -> None:
        """calculate_performance_fee（損失）の戻り値の型が正確に Decimal であること（int/float の 0 でない）。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("8000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert type(result) is Decimal
        assert result == Decimal("0")
        # 念のため int/float でないことも明示的に確認
        assert not isinstance(result, float)
        assert not isinstance(result, int)
