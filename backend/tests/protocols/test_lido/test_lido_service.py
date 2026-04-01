"""Lido サービス層のビジネスロジックテスト。"""

import logging
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.lido.client import DummyLidoClient
from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import LidoStakeRequest, TxResult
from app.protocols.lido.service import LidoService


@pytest.fixture
def config() -> LidoConfig:
    return LidoConfig(sandbox=True, peg_deviation_warn_pct=2.0)


@pytest.fixture
def dummy_client(config: LidoConfig) -> DummyLidoClient:
    return DummyLidoClient(config)


@pytest.fixture
def service(dummy_client: DummyLidoClient, config: LidoConfig) -> LidoService:
    return LidoService(client=dummy_client, config=config)


class TestLidoServiceStake:
    @pytest.mark.asyncio
    async def test_dry_run_default_true(self, service: LidoService) -> None:
        request = LidoStakeRequest(amount_eth=Decimal("0.1"))
        assert request.dry_run is True
        response = await service.stake(request)
        assert response.dry_run is True
        assert response.tx_hash is None

    @pytest.mark.asyncio
    async def test_dry_run_returns_simulated_response(self, service: LidoService) -> None:
        request = LidoStakeRequest(amount_eth=Decimal("0.5"), dry_run=True)
        response = await service.stake(request)
        assert response.operation == "STAKE"
        assert response.amount_eth == Decimal("0.5")
        assert response.received_steth == Decimal("0.5")
        assert response.staking_apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_non_dry_run_executes_stake(self, service: LidoService) -> None:
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=False)
        response = await service.stake(request)
        assert response.dry_run is False
        assert response.tx_hash is not None
        assert response.operation == "STAKE"

    @pytest.mark.asyncio
    async def test_peg_deviation_warning_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """peg 乖離 > warn_pct (1%) かつ <= 2% で WARNING ログが出ることを確認。"""
        warn_config = LidoConfig(sandbox=True, peg_deviation_warn_pct=1.0)
        mock_client = AsyncMock()
        mock_client.get_steth_eth_ratio.return_value = Decimal("0.985")  # 1.5% deviation
        mock_client.get_staking_apr.return_value = Decimal("3.5")
        mock_client.stake_eth.return_value = TxResult(
            tx_hash="0x" + "ab" * 32, success=True, received_steth_wei=100_000_000_000_000_000
        )
        svc = LidoService(client=mock_client, config=warn_config)
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=True)

        with caplog.at_level(logging.WARNING, logger="app.protocols.lido.service"):
            await svc.stake(request)
        assert any("ペグ乖離警告" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stake_blocked_on_critical_peg_deviation(self, config: LidoConfig) -> None:
        """peg 乖離 > 2% (ratio=0.97, 3% deviation) でステーキングがブロックされること。"""
        mock_client = AsyncMock()
        mock_client.get_steth_eth_ratio.return_value = Decimal("0.97")  # 3% deviation
        mock_client.get_staking_apr.return_value = Decimal("3.5")
        svc = LidoService(client=mock_client, config=config)
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=True)

        with pytest.raises(ValueError, match="Staking blocked"):
            await svc.stake(request)

    @pytest.mark.asyncio
    async def test_stake_allowed_on_minor_peg_deviation(self, config: LidoConfig) -> None:
        """peg 乖離 <= 2% (ratio=0.99, 1% deviation) でステーキングが正常に進むこと。"""
        mock_client = AsyncMock()
        mock_client.get_steth_eth_ratio.return_value = Decimal("0.99")  # 1% deviation
        mock_client.get_staking_apr.return_value = Decimal("3.5")
        svc = LidoService(client=mock_client, config=config)
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=True)

        response = await svc.stake(request)
        assert response is not None
        assert response.dry_run is True

    @pytest.mark.asyncio
    async def test_no_peg_deviation_warning_when_normal(
        self, config: LidoConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        """peg 乖離 <= 2% では WARNING ログが出ないことを確認。"""
        mock_client = AsyncMock()
        mock_client.get_steth_eth_ratio.return_value = Decimal("1.0")  # no deviation
        mock_client.get_staking_apr.return_value = Decimal("3.5")
        svc = LidoService(client=mock_client, config=config)
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=True)

        with caplog.at_level(logging.WARNING, logger="app.protocols.lido.service"):
            await svc.stake(request)
        assert not any("ペグ乖離警告" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stake_failure_raises_runtime_error(self, config: LidoConfig) -> None:
        mock_client = AsyncMock()
        mock_client.get_steth_eth_ratio.return_value = Decimal("1.0")
        mock_client.get_staking_apr.return_value = Decimal("3.5")
        mock_client.stake_eth.return_value = TxResult(success=False, error="送信失敗")
        svc = LidoService(client=mock_client, config=config)
        request = LidoStakeRequest(amount_eth=Decimal("0.1"), dry_run=False)

        with pytest.raises(RuntimeError, match="Lido ステーキング失敗"):
            await svc.stake(request)

    @pytest.mark.asyncio
    async def test_decimal_precision_in_stake(self, service: LidoService) -> None:
        """Decimal 精度が保たれることを確認（float 変換なし）。"""
        amount = Decimal("0.123456789012345678")
        request = LidoStakeRequest(amount_eth=amount, dry_run=True)
        response = await service.stake(request)
        assert isinstance(response.amount_eth, Decimal)
        assert isinstance(response.received_steth, Decimal)
        assert isinstance(response.staking_apr, Decimal)


class TestLidoServiceGetStatus:
    @pytest.mark.asyncio
    async def test_get_status_returns_lido_status(self, service: LidoService) -> None:
        status = await service.get_status()
        assert status.sandbox is True
        assert status.chain == "holesky"
        assert isinstance(status.steth_balance, Decimal)
        assert isinstance(status.staking_apr, Decimal)
        assert isinstance(status.steth_eth_ratio, Decimal)
        assert isinstance(status.peg_deviation_pct, Decimal)

    @pytest.mark.asyncio
    async def test_peg_deviation_is_zero_for_dummy(self, service: LidoService) -> None:
        status = await service.get_status()
        assert status.peg_deviation_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_apr_returns_correct_structure(self, service: LidoService) -> None:
        apr_response = await service.get_apr()
        assert apr_response.staking_apr == Decimal("3.5")
        assert apr_response.source == "dummy"
