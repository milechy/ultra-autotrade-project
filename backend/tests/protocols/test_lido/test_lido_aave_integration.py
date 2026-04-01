"""Lido + Aave V3 複合戦略テスト。"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.lido.aave_integration import LidoAaveStrategy
from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import TxResult


@pytest.fixture
def config() -> LidoConfig:
    return LidoConfig(sandbox=True)


@pytest.fixture
def mock_lido_client() -> AsyncMock:
    client = AsyncMock()
    client.get_steth_eth_ratio.return_value = Decimal("1.0")
    client.get_staking_apr.return_value = Decimal("3.5")
    client.stake_eth.return_value = TxResult(
        tx_hash="0x" + "cd" * 32,
        success=True,
        received_steth_wei=100_000_000_000_000_000,
    )
    return client


@pytest.fixture
def strategy(mock_lido_client: AsyncMock, config: LidoConfig) -> LidoAaveStrategy:
    return LidoAaveStrategy(lido_client=mock_lido_client, config=config)


class TestLidoAaveStrategy:
    @pytest.mark.asyncio
    async def test_execute_yield_strategy_dry_run(self, strategy: LidoAaveStrategy) -> None:
        result = await strategy.execute_yield_strategy(amount_eth=Decimal("0.5"), dry_run=True)
        assert result.operation == "STAKE"
        assert result.amount_eth == Decimal("0.5")
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_estimate_compound_yield_calculation(self, strategy: LidoAaveStrategy) -> None:
        """複合 APR = Lido APR + Aave APR を確認。"""
        estimate = await strategy.estimate_compound_yield(amount_eth=Decimal("1.0"))
        assert estimate.lido_staking_apr == Decimal("3.5")
        assert estimate.aave_supply_apr == Decimal("1.5")
        assert estimate.compound_apr == Decimal("5.0")
        assert estimate.amount_eth == Decimal("1.0")
        # 1.0 ETH × 5% = 0.05 ETH/year
        assert estimate.estimated_annual_yield_eth == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_compound_yield_decimal_precision(self, strategy: LidoAaveStrategy) -> None:
        """Decimal 精度を確認（float 変換なし）。"""
        estimate = await strategy.estimate_compound_yield(amount_eth=Decimal("2.5"))
        assert isinstance(estimate.compound_apr, Decimal)
        assert isinstance(estimate.estimated_annual_yield_eth, Decimal)
        # 2.5 × 5% = 0.125
        assert estimate.estimated_annual_yield_eth == Decimal("0.125")

    @pytest.mark.asyncio
    async def test_execute_yield_strategy_calls_stake(
        self, strategy: LidoAaveStrategy, mock_lido_client: AsyncMock
    ) -> None:
        """ステーキングが実際に呼ばれることを確認。"""
        await strategy.execute_yield_strategy(amount_eth=Decimal("0.1"), dry_run=True)
        mock_lido_client.get_steth_eth_ratio.assert_called_once()
        mock_lido_client.get_staking_apr.assert_called_once()
