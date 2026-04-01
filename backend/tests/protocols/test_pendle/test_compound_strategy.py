"""Lido + Pendle 複合戦略のユニットテスト。"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.strategy import LidoPendleCompoundStrategy


@pytest.fixture
def mock_lido_client() -> AsyncMock:
    client = AsyncMock()
    client.get_staking_apr.return_value = Decimal("3.5")
    client.get_steth_eth_ratio.return_value = Decimal("1.0")
    client.get_steth_balance.return_value = Decimal("1.0")
    return client


@pytest.fixture
def mock_pendle_client() -> AsyncMock:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.protocols.pendle.schemas import PendleMarketInfo  # noqa: PLC0415

    client = AsyncMock()
    market_info = PendleMarketInfo(
        market_address="0x" + "0" * 40,
        underlying_asset="stETH",
        maturity=datetime.now(tz=timezone.utc) + timedelta(days=30),
        days_to_maturity=30,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal("0.95"),
        yt_price=Decimal("0.05"),
        tvl_usd=Decimal("50000000"),
    )
    client.get_market_info.return_value = market_info
    client.get_pt_price.return_value = Decimal("0.95")
    client.get_yt_price.return_value = Decimal("0.05")
    client.mint_sy.return_value = {
        "success": True,
        "sy_received": Decimal("1.0"),
        "tx_hash": "0x" + "aa" * 32,
    }
    client.mint_pt_yt.return_value = {
        "success": True,
        "pt_received": Decimal("1.052631578947368421"),
        "yt_received": Decimal("20.0"),
        "tx_hash": "0x" + "bb" * 32,
    }
    return client


@pytest.fixture
def strategy(
    mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
) -> LidoPendleCompoundStrategy:
    return LidoPendleCompoundStrategy(
        lido_client=mock_lido_client,
        pendle_client=mock_pendle_client,
    )


class TestLidoPendleCompoundStrategyExecute:
    @pytest.mark.asyncio
    async def test_execute_dry_run_returns_result(
        self, strategy: LidoPendleCompoundStrategy
    ) -> None:
        result = await strategy.execute(
            amount_eth=Decimal("1.0"),
            strategy="pt_fixed",
            dry_run=True,
        )
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_execute_steps_list_populated(self, strategy: LidoPendleCompoundStrategy) -> None:
        """steps リストが空でないことを確認。"""
        result = await strategy.execute(
            amount_eth=Decimal("1.0"),
            strategy="pt_fixed",
            dry_run=True,
        )
        assert len(result.steps) >= 2  # Step 1 + Step 2

    @pytest.mark.asyncio
    async def test_execute_pt_fixed_total_apy_is_decimal(
        self, strategy: LidoPendleCompoundStrategy
    ) -> None:
        result = await strategy.execute(
            amount_eth=Decimal("1.0"),
            strategy="pt_fixed",
            dry_run=True,
        )
        assert type(result.total_expected_apy) is Decimal

    @pytest.mark.asyncio
    async def test_execute_yt_leverage_dry_run(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.execute(
            amount_eth=Decimal("1.0"),
            strategy="yt_leverage",
            dry_run=True,
        )
        assert result.dry_run is True
        assert len(result.steps) >= 2

    @pytest.mark.asyncio
    async def test_execute_final_position_contains_pt(
        self, strategy: LidoPendleCompoundStrategy
    ) -> None:
        """pt_fixed 戦略では final_position に 'PT' が含まれる。"""
        result = await strategy.execute(
            amount_eth=Decimal("1.0"),
            strategy="pt_fixed",
            dry_run=True,
        )
        assert "PT" in result.final_position


class TestLidoPendleCompareStrategies:
    @pytest.mark.asyncio
    async def test_compare_returns_3_strategies(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.compare_strategies(
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        assert len(result.strategies) == 3

    @pytest.mark.asyncio
    async def test_compare_strategy_names(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.compare_strategies(
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        names = {s.strategy for s in result.strategies}
        assert "aave_only" in names
        assert "lido_aave" in names
        assert "lido_pendle_pt" in names

    @pytest.mark.asyncio
    async def test_lido_pendle_pt_has_highest_apy(
        self, strategy: LidoPendleCompoundStrategy
    ) -> None:
        """Lido + Pendle PT の APY が最も高いことを確認。"""
        result = await strategy.compare_strategies(
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        apy_map = {s.strategy: s.expected_apy for s in result.strategies}
        # lido+pendle = lido_apr + fixed_yield (≈ 3.5 + 64.04 = 67.54%)
        # lido+aave = 3.5 + 1.5 = 5.0%
        # aave_only = 1.5%
        assert apy_map["lido_pendle_pt"] > apy_map["lido_aave"]
        assert apy_map["lido_pendle_pt"] > apy_map["aave_only"]

    @pytest.mark.asyncio
    async def test_best_strategy_is_lido_pendle(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.compare_strategies(
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        assert result.best_strategy == "lido_pendle_pt"

    @pytest.mark.asyncio
    async def test_compare_all_apy_are_decimal(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.compare_strategies(
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        for s in result.strategies:
            assert type(s.expected_apy) is Decimal

    @pytest.mark.asyncio
    async def test_compare_amount_is_decimal(self, strategy: LidoPendleCompoundStrategy) -> None:
        result = await strategy.compare_strategies(
            amount=Decimal("2.5"),
            market_address="0x" + "0" * 40,
        )
        assert type(result.amount) is Decimal
        assert result.amount == Decimal("2.5")
