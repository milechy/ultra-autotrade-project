"""Pendle Finance 戦略評価のユニットテスト。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.pendle.strategy import (
    PendleFixedYieldStrategy,
    PendleYieldLeverageStrategy,
)


@pytest.fixture
def dummy_market_info() -> PendleMarketInfo:
    return PendleMarketInfo(
        market_address="0x" + "0" * 40,
        underlying_asset="stETH",
        maturity=datetime.now(tz=timezone.utc) + timedelta(days=30),
        days_to_maturity=30,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal("0.95"),
        yt_price=Decimal("0.05"),
        tvl_usd=Decimal("50000000"),
    )


class TestPendleFixedYieldStrategy:
    @pytest.mark.asyncio
    async def test_recommends_when_yield_greater_than_aave(
        self, dummy_market_info: PendleMarketInfo
    ) -> None:
        """固定利回りが Aave APR を上回る場合は推奨。"""
        strategy = PendleFixedYieldStrategy()
        # pt_price=0.95, days=30 → yield ≈ 64.04%  >> aave=1.5%
        aave_apr = Decimal("1.5")
        result = await strategy.evaluate(dummy_market_info, aave_apr)
        assert result.recommended is True

    @pytest.mark.asyncio
    async def test_does_not_recommend_when_yield_less_than_aave(self) -> None:
        """固定利回りが Aave APR を下回る場合は非推奨。"""
        strategy = PendleFixedYieldStrategy()
        # pt_price=0.999 (0.1% ディスカウント), days=30 → yield ≈ 1.2% < aave=5%
        market_info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=datetime.now(tz=timezone.utc) + timedelta(days=30),
            days_to_maturity=30,
            implied_apy=Decimal("1.2"),
            pt_price=Decimal("0.999"),
            yt_price=Decimal("0.001"),
            tvl_usd=Decimal("50000000"),
        )
        aave_apr = Decimal("5.0")
        result = await strategy.evaluate(market_info, aave_apr)
        assert result.recommended is False

    @pytest.mark.asyncio
    async def test_risk_level_is_low(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleFixedYieldStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("1.5"))
        assert result.risk_level == "low"

    @pytest.mark.asyncio
    async def test_expected_apy_is_decimal(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleFixedYieldStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("1.5"))
        assert type(result.expected_apy) is Decimal

    @pytest.mark.asyncio
    async def test_strategy_name_is_pt_fixed(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleFixedYieldStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("1.5"))
        assert result.strategy == "pt_fixed"

    @pytest.mark.asyncio
    async def test_expected_apy_calculation(self, dummy_market_info: PendleMarketInfo) -> None:
        """expected_apy = (1 - pt_price) / pt_price * (365 / days) * 100"""
        strategy = PendleFixedYieldStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("1.5"))
        expected = (
            (Decimal("1") - Decimal("0.95"))
            / Decimal("0.95")
            * (Decimal("365") / Decimal("30"))
            * Decimal("100")
        )
        assert result.expected_apy == expected


class TestPendleYieldLeverageStrategy:
    @pytest.mark.asyncio
    async def test_risk_level_is_high(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleYieldLeverageStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("3.5"))
        assert result.risk_level == "high"

    @pytest.mark.asyncio
    async def test_not_recommended_even_when_profitable(
        self, dummy_market_info: PendleMarketInfo
    ) -> None:
        """高リスクのため、利益が出る場合でも recommended=False。"""
        strategy = PendleYieldLeverageStrategy()
        # staking_apr = 100% >> breakeven
        result = await strategy.evaluate(dummy_market_info, Decimal("100.0"))
        assert result.recommended is False

    @pytest.mark.asyncio
    async def test_strategy_name_is_yt_leverage(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleYieldLeverageStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("3.5"))
        assert result.strategy == "yt_leverage"

    @pytest.mark.asyncio
    async def test_breakeven_calculation(self, dummy_market_info: PendleMarketInfo) -> None:
        """ブレークイーブン = yt_price * (365 / days) * 100"""
        strategy = PendleYieldLeverageStrategy()
        # yt_price=0.05, days=30
        expected_breakeven = Decimal("0.05") * (Decimal("365") / Decimal("30")) * Decimal("100")
        # staking_apr をブレークイーブンより低く設定 → 損益分岐を下回る
        result = await strategy.evaluate(dummy_market_info, expected_breakeven - Decimal("1"))
        # 損益分岐を下回るため details に言及されているはず
        assert "ブレークイーブン" in result.details

    @pytest.mark.asyncio
    async def test_expected_apy_is_decimal(self, dummy_market_info: PendleMarketInfo) -> None:
        strategy = PendleYieldLeverageStrategy()
        result = await strategy.evaluate(dummy_market_info, Decimal("3.5"))
        assert type(result.expected_apy) is Decimal
