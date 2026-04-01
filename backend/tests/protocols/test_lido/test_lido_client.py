"""DummyLidoClient のユニットテスト。"""

from decimal import Decimal

import pytest

from app.protocols.lido.client import DummyLidoClient, LidoClient, get_lido_client
from app.protocols.lido.config import LidoConfig


@pytest.fixture
def dummy_config() -> LidoConfig:
    return LidoConfig(sandbox=True)


@pytest.fixture
def dummy_client(dummy_config: LidoConfig) -> DummyLidoClient:
    return DummyLidoClient(dummy_config)


class TestDummyLidoClient:
    @pytest.mark.asyncio
    async def test_stake_eth_returns_success(self, dummy_client: DummyLidoClient) -> None:
        result = await dummy_client.stake_eth(amount_wei=100_000_000_000_000_000)
        assert result.success is True
        assert result.tx_hash is not None
        assert result.received_steth_wei == 100_000_000_000_000_000

    @pytest.mark.asyncio
    async def test_stake_eth_tx_hash_format(self, dummy_client: DummyLidoClient) -> None:
        result = await dummy_client.stake_eth(amount_wei=1_000_000_000_000_000)
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")

    @pytest.mark.asyncio
    async def test_get_steth_balance_returns_decimal(self, dummy_client: DummyLidoClient) -> None:
        balance = await dummy_client.get_steth_balance("0x0000000000000000000000000000000000000001")
        assert isinstance(balance, Decimal)
        assert balance >= Decimal("0")

    @pytest.mark.asyncio
    async def test_get_staking_apr_returns_35(self, dummy_client: DummyLidoClient) -> None:
        apr = await dummy_client.get_staking_apr()
        assert apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_get_steth_eth_ratio_is_one(self, dummy_client: DummyLidoClient) -> None:
        ratio = await dummy_client.get_steth_eth_ratio()
        assert ratio == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_no_float_in_calculations(self, dummy_client: DummyLidoClient) -> None:
        """金額計算で float が使われていないことを確認。"""
        balance = await dummy_client.get_steth_balance("0x1234")
        apr = await dummy_client.get_staking_apr()
        ratio = await dummy_client.get_steth_eth_ratio()
        assert type(balance) is Decimal
        assert type(apr) is Decimal
        assert type(ratio) is Decimal


class TestGetLidoClient:
    def test_sandbox_returns_dummy_client(self) -> None:
        config = LidoConfig(sandbox=True)
        client = get_lido_client(config)
        assert isinstance(client, DummyLidoClient)

    def test_non_sandbox_returns_lido_client(self) -> None:
        config = LidoConfig(sandbox=False)
        client = get_lido_client(config)
        assert isinstance(client, LidoClient)

    def test_production_env_with_sandbox_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=production + sandbox=True でエラーが発生すること。"""
        monkeypatch.setenv("APP_ENV", "production")
        config = LidoConfig(sandbox=True)
        with pytest.raises(RuntimeError, match="DummyClient cannot be used in production"):
            get_lido_client(config)

    def test_staging_env_with_sandbox_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=staging + sandbox=True でエラーが発生すること。"""
        monkeypatch.setenv("APP_ENV", "staging")
        config = LidoConfig(sandbox=True)
        with pytest.raises(RuntimeError, match="DummyClient cannot be used in staging"):
            get_lido_client(config)

    def test_development_env_with_sandbox_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=development + sandbox=True は正常動作すること。"""
        monkeypatch.setenv("APP_ENV", "development")
        config = LidoConfig(sandbox=True)
        client = get_lido_client(config)
        assert isinstance(client, DummyLidoClient)
