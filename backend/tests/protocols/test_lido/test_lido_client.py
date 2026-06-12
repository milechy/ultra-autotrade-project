"""DummyLidoClient / LidoClient のユニットテスト。"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_withdraw_returns_success(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.withdraw は成功を返すこと。"""
        result = await dummy_client.withdraw(Decimal("0.5"), "stETH")
        assert result.success is True
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_withdraw_amount_preserved(self, dummy_client: DummyLidoClient) -> None:
        """withdraw の amount が TransactionResult に保持されること。"""
        amount = Decimal("1.23")
        result = await dummy_client.withdraw(amount, "stETH")
        assert result.amount == amount

    @pytest.mark.asyncio
    async def test_withdraw_eth_asset_accepted(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient は ETH アセットも受け付けること。"""
        result = await dummy_client.withdraw(Decimal("0.1"), "ETH")
        assert result.success is True


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

    def test_staging_env_with_sandbox_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Phase 1 期間中、APP_ENV=staging + sandbox=True は DummyClient を返すこと（docs/13 §1.4）。"""
        monkeypatch.setenv("APP_ENV", "staging")
        config = LidoConfig(sandbox=True)
        client = get_lido_client(config)
        assert isinstance(client, DummyLidoClient)

    def test_development_env_with_sandbox_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=development + sandbox=True は正常動作すること。"""
        monkeypatch.setenv("APP_ENV", "development")
        config = LidoConfig(sandbox=True)
        client = get_lido_client(config)
        assert isinstance(client, DummyLidoClient)


_TEST_WALLET = "0x0000000000000000000000000000000000000001"


@pytest.fixture
def real_client() -> LidoClient:
    return LidoClient(LidoConfig(sandbox=False))


class TestLidoClientApr:
    """LidoClient.get_staking_apr の Lido API 実装テスト（HTTP は mock）。"""

    @pytest.mark.asyncio
    async def test_apr_returns_real_value_from_api(self, real_client: LidoClient) -> None:
        """API 成功時に実値が Decimal で返ること。"""
        with patch.object(
            real_client,
            "_fetch_apr_data",
            new=AsyncMock(return_value={"data": {"smaApr": 2.9}}),
        ):
            apr = await real_client.get_staking_apr()
        assert apr == Decimal("2.9")
        assert type(apr) is Decimal

    @pytest.mark.asyncio
    async def test_apr_api_failure_falls_back_to_35(self, real_client: LidoClient) -> None:
        """API 失敗時にフォールバック値 3.5 が返ること。"""
        with patch.object(
            real_client,
            "_fetch_apr_data",
            new=AsyncMock(side_effect=Exception("connection error")),
        ):
            apr = await real_client.get_staking_apr()
        assert apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_apr_abnormal_value_falls_back_to_35(self, real_client: LidoClient) -> None:
        """異常値（smaApr=999 > 50）はフォールバック値 3.5 が返ること。"""
        with patch.object(
            real_client,
            "_fetch_apr_data",
            new=AsyncMock(return_value={"data": {"smaApr": 999}}),
        ):
            apr = await real_client.get_staking_apr()
        assert apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_apr_never_raises_on_malformed_response(self, real_client: LidoClient) -> None:
        """レスポンス構造が壊れていても例外が漏洩しないこと（fail-open）。"""
        with patch.object(
            real_client,
            "_fetch_apr_data",
            new=AsyncMock(return_value={}),
        ):
            apr = await real_client.get_staking_apr()  # KeyError が漏洩しないこと
        assert apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_apr_fail_open_with_unreachable_url(self) -> None:
        """到達不能な API URL でもフォールバック値 3.5 が返ること（実証）。"""
        client = LidoClient(LidoConfig(sandbox=False, api_base_url="http://127.0.0.1:1"))
        apr = await client.get_staking_apr()
        assert apr == Decimal("3.5")


class TestGetPosition:
    """AbstractLidoClient.get_position のテスト。"""

    @pytest.mark.asyncio
    async def test_dummy_client_position_returns_balance(self) -> None:
        """DummyLidoClient は stub 残高 1.0 を position に反映すること。"""
        client = DummyLidoClient(LidoConfig(sandbox=True, wallet_address=_TEST_WALLET))
        position = await client.get_position()
        assert position.protocol_name == "lido"
        assert position.asset == "stETH"
        assert position.balance == Decimal("1.0")
        assert position.value_usd == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_lido_client_position_reflects_real_balance(self) -> None:
        """LidoClient は get_steth_balance の実値を position に反映すること。"""
        client = LidoClient(LidoConfig(sandbox=False, wallet_address=_TEST_WALLET))
        with patch.object(
            client,
            "get_steth_balance",
            new=AsyncMock(return_value=Decimal("2.5")),
        ):
            position = await client.get_position()
        assert position.balance == Decimal("2.5")
        assert position.value_usd == Decimal("2.5")
        assert type(position.balance) is Decimal

    @pytest.mark.asyncio
    async def test_empty_wallet_address_returns_zero_position(self) -> None:
        """wallet_address 未設定の場合 zero position を返すこと。"""
        client = DummyLidoClient(LidoConfig(sandbox=True, wallet_address=""))
        position = await client.get_position()
        assert position.balance == Decimal("0")
        assert position.value_usd == Decimal("0")

    @pytest.mark.asyncio
    async def test_balance_failure_returns_zero_position(self) -> None:
        """get_steth_balance 例外時に fail-open で zero position を返すこと。"""
        client = LidoClient(LidoConfig(sandbox=False, wallet_address=_TEST_WALLET))
        with patch.object(
            client,
            "get_steth_balance",
            new=AsyncMock(side_effect=RuntimeError("stETH 残高取得失敗")),
        ):
            position = await client.get_position()
        assert position.balance == Decimal("0")
        assert position.value_usd == Decimal("0")


class TestLidoClientGetStethEthRatio:
    """LidoClient.get_steth_eth_ratio の on-chain call テスト（Web3 は mock）。"""

    def _make_initialized_client(self) -> LidoClient:
        """初期化済み LidoClient を返すヘルパー。"""
        client = LidoClient(LidoConfig(sandbox=False))
        mock_contract = MagicMock()
        client._contract = mock_contract
        client._initialized = True
        return client

    @pytest.mark.asyncio
    async def test_ratio_normal_case_returns_decimal(self) -> None:
        """正常系: getTotalPooledEther / getTotalShares が Decimal で返ること。"""
        client = self._make_initialized_client()
        # 100 ETH pooled, 95 shares -> ratio = 100/95
        client._contract.functions.getTotalPooledEther.return_value.call.return_value = (
            100_000_000_000_000_000_000
        )
        client._contract.functions.getTotalShares.return_value.call.return_value = (
            95_000_000_000_000_000_000
        )

        ratio = await client.get_steth_eth_ratio()

        expected = Decimal(100_000_000_000_000_000_000) / Decimal(95_000_000_000_000_000_000)
        assert ratio == expected
        assert type(ratio) is Decimal

    @pytest.mark.asyncio
    async def test_ratio_total_shares_zero_returns_one(self) -> None:
        """total_shares == 0 のとき Decimal("1") を返すこと（fail-open）。"""
        client = self._make_initialized_client()
        client._contract.functions.getTotalPooledEther.return_value.call.return_value = 0
        client._contract.functions.getTotalShares.return_value.call.return_value = 0

        ratio = await client.get_steth_eth_ratio()

        assert ratio == Decimal("1")
        assert type(ratio) is Decimal

    @pytest.mark.asyncio
    async def test_ratio_rpc_failure_raises_runtime_error(self) -> None:
        """RPC 呼出し失敗時に RuntimeError が raise されること。"""
        client = self._make_initialized_client()
        client._contract.functions.getTotalPooledEther.return_value.call.side_effect = Exception(
            "connection refused"
        )

        with pytest.raises(RuntimeError, match="stETH/ETH レート取得失敗"):
            await client.get_steth_eth_ratio()

    @pytest.mark.asyncio
    async def test_ratio_total_shares_call_failure_raises_runtime_error(self) -> None:
        """getTotalShares RPC 失敗時も RuntimeError が raise されること。"""
        client = self._make_initialized_client()
        client._contract.functions.getTotalPooledEther.return_value.call.return_value = (
            100_000_000_000_000_000_000
        )
        client._contract.functions.getTotalShares.return_value.call.side_effect = Exception(
            "RPC timeout"
        )

        with pytest.raises(RuntimeError, match="stETH/ETH レート取得失敗"):
            await client.get_steth_eth_ratio()


class TestLidoClientGetStethBalance:
    """LidoClient.get_steth_balance の on-chain call テスト（Web3 は mock）。"""

    def _make_initialized_client(self) -> LidoClient:
        """初期化済み LidoClient を返すヘルパー。"""
        client = LidoClient(LidoConfig(sandbox=False))
        mock_contract = MagicMock()
        client._contract = mock_contract
        client._initialized = True
        return client

    @pytest.mark.asyncio
    async def test_balance_normal_case_returns_decimal(self) -> None:
        """正常系: balanceOf の返値が ETH 単位の Decimal で返ること。"""
        client = self._make_initialized_client()
        # 2.5 ETH = 2_500_000_000_000_000_000 Wei
        client._contract.functions.balanceOf.return_value.call.return_value = (
            2_500_000_000_000_000_000
        )

        with patch("web3.Web3.to_checksum_address", side_effect=lambda x: x):
            balance = await client.get_steth_balance(_TEST_WALLET)

        assert balance == Decimal("2.5")
        assert type(balance) is Decimal

    @pytest.mark.asyncio
    async def test_balance_rpc_failure_raises_runtime_error(self) -> None:
        """RPC 呼出し失敗時に RuntimeError が raise されること。"""
        client = self._make_initialized_client()
        client._contract.functions.balanceOf.return_value.call.side_effect = Exception(
            "RPC connection error"
        )

        with patch("web3.Web3.to_checksum_address", side_effect=lambda x: x):
            with pytest.raises(RuntimeError, match="stETH 残高取得失敗"):
                await client.get_steth_balance(_TEST_WALLET)

    @pytest.mark.asyncio
    async def test_balance_invalid_address_raises_runtime_error(self) -> None:
        """無効なアドレスで ValueError が RuntimeError としてラップされること。"""
        client = self._make_initialized_client()

        # to_checksum_address が無効アドレスで ValueError を raise するケース
        with patch(
            "web3.Web3.to_checksum_address",
            side_effect=ValueError("invalid address"),
        ):
            with pytest.raises(RuntimeError, match="stETH 残高取得失敗"):
                await client.get_steth_balance("not-a-valid-address")
