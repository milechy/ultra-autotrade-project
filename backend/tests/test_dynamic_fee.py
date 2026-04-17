# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_dynamic_fee.py
"""calculate_dynamic_fee() のユニットテスト。"""

from decimal import Decimal

import pytest

from app.billing.dynamic_fee import DynamicFeeResult, calculate_dynamic_fee


class TestCalculateDynamicFeeENBNonPositive:
    """ENB ≤ 0 のケース: should_trade = False。"""

    def test_enb_zero_returns_no_trade(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("0"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.should_trade is False
        assert result.fee_rate == Decimal("0")
        assert result.fee_amount == Decimal("0")
        assert result.net_trade_amount == Decimal("1000")

    def test_enb_negative_returns_no_trade(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("-50"),
            tier="UPPER",
            trade_amount_usd=Decimal("5000"),
        )
        assert result.should_trade is False
        assert result.fee_rate == Decimal("0")
        assert result.fee_amount == Decimal("0")

    def test_enb_very_small_negative(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("-0.000001"),
            tier="GENERAL",
            trade_amount_usd=Decimal("100"),
        )
        assert result.should_trade is False


class TestCalculateDynamicFeeGeneral:
    """GENERAL ティア (3〜10%) のケース。"""

    def test_enb_ratio_zero_gives_base_rate(self) -> None:
        # enb_ratio ≈ 0 → fee_rate ≈ base_rate (0.03)
        result = calculate_dynamic_fee(
            enb=Decimal("0.001"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.should_trade is True
        assert result.tier == "GENERAL"
        assert Decimal("0.03") <= result.fee_rate <= Decimal("0.10")

    def test_enb_ratio_half_gives_midpoint(self) -> None:
        # enb_ratio = 0.5 → fee_rate = 0.03 + 0.5 * 0.07 = 0.065
        result = calculate_dynamic_fee(
            enb=Decimal("500"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.should_trade is True
        assert Decimal("0.064") <= result.fee_rate <= Decimal("0.066")

    def test_enb_ratio_one_gives_max_rate(self) -> None:
        # enb_ratio = 1.0 → fee_rate = 0.10
        result = calculate_dynamic_fee(
            enb=Decimal("1000"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.10")

    def test_enb_exceeds_trade_amount_clamps_to_one(self) -> None:
        # enb > trade_amount → enb_ratio clamped to 1.0 → max_rate
        result = calculate_dynamic_fee(
            enb=Decimal("9999"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.10")

    def test_fee_rate_within_range(self) -> None:
        for enb in [Decimal("10"), Decimal("100"), Decimal("999")]:
            result = calculate_dynamic_fee(
                enb=enb, tier="GENERAL", trade_amount_usd=Decimal("1000")
            )
            assert Decimal("0.03") <= result.fee_rate <= Decimal("0.10")

    def test_fee_amount_calculation(self) -> None:
        # enb_ratio = 1.0 → fee_rate = 0.10 → fee_amount = 1000 * 0.10 = 100
        result = calculate_dynamic_fee(
            enb=Decimal("1000"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert result.fee_amount == Decimal("100.00")
        assert result.net_trade_amount == Decimal("900.00")

    def test_net_trade_amount_equals_trade_minus_fee(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("500"),
            tier="GENERAL",
            trade_amount_usd=Decimal("2000"),
        )
        assert result.net_trade_amount == result.fee_amount.__class__(
            str(Decimal("2000") - result.fee_amount)
        )


class TestCalculateDynamicFeeUpper:
    """UPPER ティア (15〜25%) のケース。"""

    def test_enb_ratio_zero_gives_base_rate(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("0.001"),
            tier="UPPER",
            trade_amount_usd=Decimal("50000"),
        )
        assert result.should_trade is True
        assert result.tier == "UPPER"
        assert Decimal("0.15") <= result.fee_rate <= Decimal("0.25")

    def test_enb_ratio_half_gives_midpoint(self) -> None:
        # enb_ratio = 0.5 → fee_rate = 0.15 + 0.5 * 0.10 = 0.20
        result = calculate_dynamic_fee(
            enb=Decimal("25000"),
            tier="UPPER",
            trade_amount_usd=Decimal("50000"),
        )
        assert result.should_trade is True
        assert Decimal("0.199") <= result.fee_rate <= Decimal("0.201")

    def test_enb_ratio_one_gives_max_rate(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("50000"),
            tier="UPPER",
            trade_amount_usd=Decimal("50000"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.25")

    def test_fee_rate_within_range(self) -> None:
        for enb in [Decimal("100"), Decimal("10000"), Decimal("49999")]:
            result = calculate_dynamic_fee(enb=enb, tier="UPPER", trade_amount_usd=Decimal("50000"))
            assert Decimal("0.15") <= result.fee_rate <= Decimal("0.25")


class TestCalculateDynamicFeeDecimalPrecision:
    """Decimal精度テスト。"""

    def test_fee_amount_is_decimal(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("100"),
            tier="GENERAL",
            trade_amount_usd=Decimal("1000"),
        )
        assert isinstance(result.fee_rate, Decimal)
        assert isinstance(result.fee_amount, Decimal)
        assert isinstance(result.net_trade_amount, Decimal)

    def test_no_float_in_result(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("333.333333"),
            tier="GENERAL",
            trade_amount_usd=Decimal("999.999"),
        )
        # fee_amount は小数点2桁に丸められる
        assert result.fee_amount == result.fee_amount.quantize(Decimal("0.01"))

    def test_net_amount_non_negative(self) -> None:
        result = calculate_dynamic_fee(
            enb=Decimal("1"),
            tier="UPPER",
            trade_amount_usd=Decimal("1"),
        )
        assert result.net_trade_amount >= Decimal("0")


class TestCalculateDynamicFeeInvalidTier:
    """不正なtierのケース。"""

    def test_unknown_tier_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            calculate_dynamic_fee(
                enb=Decimal("100"),
                tier="PREMIUM",
                trade_amount_usd=Decimal("1000"),
            )

    def test_empty_tier_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            calculate_dynamic_fee(
                enb=Decimal("100"),
                tier="",
                trade_amount_usd=Decimal("1000"),
            )


class TestDynamicFeeResult:
    """DynamicFeeResult dataclass のテスト。"""

    def test_result_fields(self) -> None:
        result = DynamicFeeResult(
            fee_rate=Decimal("0.05"),
            fee_amount=Decimal("50.00"),
            net_trade_amount=Decimal("950.00"),
            should_trade=True,
            tier="GENERAL",
        )
        assert result.fee_rate == Decimal("0.05")
        assert result.fee_amount == Decimal("50.00")
        assert result.net_trade_amount == Decimal("950.00")
        assert result.should_trade is True
        assert result.tier == "GENERAL"
