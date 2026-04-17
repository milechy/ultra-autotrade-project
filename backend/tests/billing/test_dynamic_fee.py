# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/billing/test_dynamic_fee.py
"""calculate_fee_by_market() のユニットテスト (B-1)。"""

from decimal import Decimal

import pytest

from app.billing.dynamic_fee import (
    MarketCondition,
    MarketFeeResult,
    calculate_fee_by_market,
    determine_market_condition,
)

# ヘルパー: 30日保有での予想利益を計算
_HOLDING_DAYS = Decimal("30")


def _expected_profit(amount_usd: Decimal, apy: Decimal) -> Decimal:
    return amount_usd * apy / Decimal("100") * _HOLDING_DAYS / Decimal("365")


class TestDetermineMarketCondition:
    """determine_market_condition() のテスト。"""

    def test_apy_below_3_is_bear(self) -> None:
        assert determine_market_condition(Decimal("2.9")) == MarketCondition.BEAR

    def test_apy_zero_is_bear(self) -> None:
        assert determine_market_condition(Decimal("0")) == MarketCondition.BEAR

    def test_apy_3_is_stable(self) -> None:
        assert determine_market_condition(Decimal("3")) == MarketCondition.STABLE

    def test_apy_4_5_is_stable(self) -> None:
        assert determine_market_condition(Decimal("4.5")) == MarketCondition.STABLE

    def test_apy_6_is_stable(self) -> None:
        assert determine_market_condition(Decimal("6")) == MarketCondition.STABLE

    def test_apy_above_6_is_bull(self) -> None:
        assert determine_market_condition(Decimal("6.1")) == MarketCondition.BULL

    def test_apy_high_is_bull(self) -> None:
        assert determine_market_condition(Decimal("20")) == MarketCondition.BULL


class TestGeneralTierBearMarket:
    """一般層×低迷期: 手数料率 3〜5%。"""

    def test_fee_rate_in_range(self) -> None:
        amount = Decimal("5000")
        apy = Decimal("1.5")
        profit = _expected_profit(amount, apy)
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="GENERAL",
            current_apy=apy,
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.market_condition == MarketCondition.BEAR
        assert Decimal("0.03") <= result.fee_rate <= Decimal("0.05")

    def test_fee_amount_applied_to_net_profit(self) -> None:
        amount = Decimal("10000")
        apy = Decimal("2")
        profit = _expected_profit(amount, apy)
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="GENERAL",
            current_apy=apy,
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        if result.should_trade:
            net = profit - Decimal("0.27")
            expected = net * result.fee_rate
            # 実装はROUND_DOWN、差は$0.01以内
            assert abs(result.fee_amount - expected) < Decimal("0.01")


class TestGeneralTierStableMarket:
    """一般層×安定期: 手数料率 6〜10%。"""

    def test_fee_rate_in_range(self) -> None:
        amount = Decimal("5000")
        apy = Decimal("4.5")
        profit = _expected_profit(amount, apy)
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="GENERAL",
            current_apy=apy,
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.market_condition == MarketCondition.STABLE
        assert Decimal("0.06") <= result.fee_rate <= Decimal("0.10")

    def test_fee_rate_midpoint_apy(self) -> None:
        # APY=4.5%, apy_normalized=0.45 → fee_rate = 0.06 + (0.10 - 0.06) * 0.45 = 0.078
        amount = Decimal("5000")
        profit = _expected_profit(amount, Decimal("4.5"))
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="GENERAL",
            current_apy=Decimal("4.5"),
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert Decimal("0.077") <= result.fee_rate <= Decimal("0.079")


class TestUpperTierBullMarket:
    """アッパー層×好調期: 手数料率 20〜25%。"""

    def test_fee_rate_in_range(self) -> None:
        amount = Decimal("50000")
        apy = Decimal("8")
        profit = _expected_profit(amount, apy)
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="UPPER",
            current_apy=apy,
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.market_condition == MarketCondition.BULL
        assert Decimal("0.20") <= result.fee_rate <= Decimal("0.25")

    def test_fee_rate_high_apy(self) -> None:
        # APY=10%, apy_normalized=1.0 → fee_rate = 0.20 + (0.25-0.20)*1.0 = 0.25
        amount = Decimal("50000")
        profit = _expected_profit(amount, Decimal("10"))
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="UPPER",
            current_apy=Decimal("10"),
            expected_profit_usd=profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.25")


class TestNegativeProfitNoTrade:
    """純利益マイナス → should_trade=False。"""

    def test_negative_net_profit(self) -> None:
        # expected_profit < fixed_cost → net_profit < 0
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("50"),
            tier="GENERAL",
            current_apy=Decimal("4"),
            expected_profit_usd=Decimal("0.10"),  # < $0.27 fixed_cost
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is False
        assert result.fee_rate == Decimal("0")
        assert result.fee_amount == Decimal("0")

    def test_zero_net_profit(self) -> None:
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("100"),
            tier="GENERAL",
            current_apy=Decimal("3"),
            expected_profit_usd=Decimal("0.27"),  # = fixed_cost → net=0
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is False

    def test_zero_expected_profit(self) -> None:
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("1000"),
            tier="UPPER",
            current_apy=Decimal("5"),
            expected_profit_usd=Decimal("0"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is False


class TestFeeCapGeneral:
    """一般層キャップ15%を超えないこと。"""

    def test_cap_general_not_exceeded(self) -> None:
        # 高APYでもGENERAL上限15%
        for apy_val in ["5", "7", "10", "20"]:
            result = calculate_fee_by_market(
                trade_amount_usd=Decimal("5000"),
                tier="GENERAL",
                current_apy=Decimal(apy_val),
                expected_profit_usd=Decimal("100"),
                fixed_cost_usd=Decimal("0.27"),
            )
            if result.should_trade:
                assert result.fee_rate <= Decimal("0.15"), f"Cap exceeded at APY={apy_val}"

    def test_general_bull_max_rate_is_015(self) -> None:
        # BULL期 APY=10%: apy_normalized=1.0 → 0.08 + (0.15-0.08)*1.0 = 0.15
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("5000"),
            tier="GENERAL",
            current_apy=Decimal("10"),
            expected_profit_usd=Decimal("100"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.15")


class TestFeeCapUpper:
    """アッパー層キャップ25%を超えないこと。"""

    def test_cap_upper_not_exceeded(self) -> None:
        for apy_val in ["8", "10", "15", "50"]:
            result = calculate_fee_by_market(
                trade_amount_usd=Decimal("50000"),
                tier="UPPER",
                current_apy=Decimal(apy_val),
                expected_profit_usd=Decimal("500"),
                fixed_cost_usd=Decimal("0.27"),
            )
            if result.should_trade:
                assert result.fee_rate <= Decimal("0.25"), f"Cap exceeded at APY={apy_val}"

    def test_upper_bull_max_rate_is_025(self) -> None:
        # BULL期 APY=10%: fee_rate = 0.20 + (0.25-0.20)*1.0 = 0.25
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("50000"),
            tier="UPPER",
            current_apy=Decimal("10"),
            expected_profit_usd=Decimal("500"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.25")


class TestTierBoundary:
    """閾値前後でのtier判定が正しいこと（tierはcallerが渡す）。"""

    def test_general_fee_range_lower(self) -> None:
        # GENERAL/BEAR: min_rate=0.03
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("19999"),
            tier="GENERAL",
            current_apy=Decimal("0"),  # apy_normalized=0 → min_rate
            expected_profit_usd=Decimal("10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.03")

    def test_upper_fee_range_lower(self) -> None:
        # UPPER/BEAR: min_rate=0.10
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("20000"),
            tier="UPPER",
            current_apy=Decimal("0"),  # apy_normalized=0 → min_rate
            expected_profit_usd=Decimal("10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        assert result.fee_rate == Decimal("0.10")

    def test_general_and_upper_differ_at_same_apy(self) -> None:
        # 同APYでGENERAL < UPPER
        apy = Decimal("5")
        profit = Decimal("50")
        g = calculate_fee_by_market(Decimal("10000"), "GENERAL", apy, profit, Decimal("0.27"))
        u = calculate_fee_by_market(Decimal("10000"), "UPPER", apy, profit, Decimal("0.27"))
        if g.should_trade and u.should_trade:
            assert g.fee_rate < u.fee_rate


class TestMarketFeeResultFields:
    """MarketFeeResult フィールドの型・内容検証。"""

    def test_result_is_dataclass(self) -> None:
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("5000"),
            tier="GENERAL",
            current_apy=Decimal("4"),
            expected_profit_usd=Decimal("10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert isinstance(result, MarketFeeResult)

    def test_fee_rate_is_decimal(self) -> None:
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("5000"),
            tier="GENERAL",
            current_apy=Decimal("4"),
            expected_profit_usd=Decimal("10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        if result.should_trade:
            assert isinstance(result.fee_rate, Decimal)
            assert isinstance(result.fee_amount, Decimal)

    def test_fee_amount_quantized_to_cents(self) -> None:
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("5000"),
            tier="GENERAL",
            current_apy=Decimal("4"),
            expected_profit_usd=Decimal("10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        if result.should_trade:
            assert result.fee_amount == result.fee_amount.quantize(Decimal("0.01"))

    def test_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            calculate_fee_by_market(
                trade_amount_usd=Decimal("1000"),
                tier="PREMIUM",
                current_apy=Decimal("5"),
                expected_profit_usd=Decimal("10"),
                fixed_cost_usd=Decimal("0.27"),
            )
