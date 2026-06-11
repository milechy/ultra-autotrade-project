"""DummyLidoClient のユニットテスト。"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.protocols.lido.client import DummyLidoClient, LidoClient, get_lido_client
from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import (
    ClaimWithdrawalResult,
    WithdrawalRequestResult,
    WithdrawalStatus,
)


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

    # --- request_withdrawals ---

    @pytest.mark.asyncio
    async def test_request_withdrawals_returns_success(self, dummy_client: DummyLidoClient) -> None:
        """request_withdrawals が成功を返すこと。"""
        amounts_wei = [500_000_000_000_000_000]  # 0.5 ETH
        result = await dummy_client.request_withdrawals(amounts_wei)
        assert isinstance(result, WithdrawalRequestResult)
        assert result.success is True
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_request_withdrawals_returns_request_ids(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """request_withdrawals が request_ids を返すこと。"""
        amounts_wei = [100_000_000_000_000_000, 200_000_000_000_000_000]
        result = await dummy_client.request_withdrawals(amounts_wei)
        assert result.success is True
        assert len(result.request_ids) == len(amounts_wei)

    @pytest.mark.asyncio
    async def test_request_withdrawals_empty_amounts_fails(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """amounts_wei が空のとき失敗を返すこと。"""
        result = await dummy_client.request_withdrawals([])
        assert result.success is False
        assert result.error is not None

    # --- claim_withdrawal ---

    @pytest.mark.asyncio
    async def test_claim_withdrawal_returns_success(self, dummy_client: DummyLidoClient) -> None:
        """claim_withdrawal が成功を返すこと。"""
        result = await dummy_client.claim_withdrawal([1001, 1002])
        assert isinstance(result, ClaimWithdrawalResult)
        assert result.success is True
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_preserves_request_ids(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """claim_withdrawal が claimed_request_ids を返すこと。"""
        request_ids = [1001, 1002, 1003]
        result = await dummy_client.claim_withdrawal(request_ids)
        assert result.claimed_request_ids == request_ids

    @pytest.mark.asyncio
    async def test_claim_withdrawal_empty_ids_fails(self, dummy_client: DummyLidoClient) -> None:
        """request_ids が空のとき失敗を返すこと。"""
        result = await dummy_client.claim_withdrawal([])
        assert result.success is False
        assert result.error is not None

    # --- get_withdrawal_status ---

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_returns_list(self, dummy_client: DummyLidoClient) -> None:
        """get_withdrawal_status がリストを返すこと。"""
        statuses = await dummy_client.get_withdrawal_status([1001, 1002])
        assert isinstance(statuses, list)
        assert len(statuses) == 2

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_correct_fields(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """get_withdrawal_status の各フィールドが正しい型であること。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        status = statuses[0]
        assert isinstance(status, WithdrawalStatus)
        assert status.request_id == 1001
        assert isinstance(status.amount_of_steth, Decimal)
        assert isinstance(status.amount_of_shares, Decimal)
        assert isinstance(status.is_finalized, bool)
        assert isinstance(status.is_claimed, bool)
        assert isinstance(status.timestamp, int)

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_no_float(self, dummy_client: DummyLidoClient) -> None:
        """withdrawal status の金額フィールドが Decimal であること（float 禁止）。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        status = statuses[0]
        assert type(status.amount_of_steth) is Decimal
        assert type(status.amount_of_shares) is Decimal

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_dummy_is_finalized(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """DummyLidoClient の withdrawal status は is_finalized=True を返すこと。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        assert statuses[0].is_finalized is True

    # --- withdraw (AbstractLidoClient 経由) ---

    @pytest.mark.asyncio
    async def test_withdraw_delegates_to_request_withdrawals(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """AbstractLidoClient.withdraw() が request_withdrawals() に委譲すること。"""
        result = await dummy_client.withdraw(Decimal("1.0"), "stETH")
        assert result.success is True
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_withdraw_invalid_asset_fails(self, dummy_client: DummyLidoClient) -> None:
        """無効なアセットで withdraw は失敗を返すこと。"""
        result = await dummy_client.withdraw(Decimal("1.0"), "USDC")
        assert result.success is False
        assert result.error is not None


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


class TestLidoClientStakeEth:
    """LidoClient.stake_eth のモックテスト（チェーン接続なし）。"""

    @pytest.mark.asyncio
    async def test_stake_eth_no_private_key_fails(self) -> None:
        """秘密鍵未設定で stake_eth は失敗を返すこと。"""
        config = LidoConfig(sandbox=False, wallet_private_key="")
        client = LidoClient(config)
        client._initialized = True
        client._w3 = None
        client._contract = None

        result = await client.stake_eth(100_000_000_000_000_000)
        assert result.success is False
        assert "LIDO_WALLET_PRIVATE_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_stake_eth_success_with_mock(self) -> None:
        """web3 モックで stake_eth 成功パスをテスト。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        mock_receipt = {"status": 1}
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "ab" * 32

        mock_contract_fn = MagicMock()
        mock_contract_fn.build_transaction.return_value = {}

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.submit.return_value = mock_contract_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        client._w3 = mock_w3
        client._contract = mock_steth_contract
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x0000000000000000000000000000000000000000",
        ):
            result = await client.stake_eth(100_000_000_000_000_000)

        assert result.success is True
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_stake_eth_tx_status_zero_fails(self) -> None:
        """tx status=0 のとき stake_eth は失敗を返すこと。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        mock_receipt = {"status": 0}
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "ab" * 32

        mock_contract_fn = MagicMock()
        mock_contract_fn.build_transaction.return_value = {}

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.submit.return_value = mock_contract_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        client._w3 = mock_w3
        client._contract = mock_steth_contract
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x0000000000000000000000000000000000000000",
        ):
            result = await client.stake_eth(100_000_000_000_000_000)

        assert result.success is False
        assert result.error is not None


class TestLidoClientRequestWithdrawals:
    """LidoClient.request_withdrawals のモックテスト（チェーン接続なし）。"""

    @pytest.fixture
    def real_config(self) -> LidoConfig:
        return LidoConfig(
            sandbox=False,
            wallet_private_key="0x" + "aa" * 32,
        )

    @pytest.mark.asyncio
    async def test_request_withdrawals_no_private_key_fails(self) -> None:
        """秘密鍵未設定で request_withdrawals は失敗を返すこと。"""
        config = LidoConfig(sandbox=False, wallet_private_key="")
        client = LidoClient(config)
        client._initialized = True  # _ensure_initialized をスキップ
        client._w3 = None
        client._contract = None

        result = await client.request_withdrawals([100_000_000_000_000_000])
        assert result.success is False
        assert "LIDO_WALLET_PRIVATE_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_request_withdrawals_empty_amounts_fails(self) -> None:
        """amounts_wei が空で request_withdrawals は失敗を返すこと。"""
        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)
        client._initialized = True
        client._w3 = None
        client._contract = None

        result = await client.request_withdrawals([])
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_request_withdrawals_web3_exception_returns_failure(self) -> None:
        """web3 呼び出しで例外が出たとき失敗を返すこと。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.side_effect = ValueError("invalid key")
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        # Web3 は遅延 import されるため、_w3 への side_effect で例外を発生させる
        result = await client.request_withdrawals([100_000_000_000_000_000])

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_request_withdrawals_success_with_mock(self) -> None:
        """web3 モックで request_withdrawals 成功パスをテスト。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        approve_receipt = {"status": 1}
        withdraw_receipt = {"status": 1}
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "cd" * 32

        mock_approve_fn = MagicMock()
        mock_approve_fn.build_transaction.return_value = {}

        mock_withdraw_fn = MagicMock()
        mock_withdraw_fn.build_transaction.return_value = {}

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.approve.return_value = mock_approve_fn

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.requestWithdrawals.return_value = mock_withdraw_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 10
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.side_effect = [
            approve_receipt,
            withdraw_receipt,
        ]
        mock_w3.eth.contract.return_value = mock_queue_contract

        client._w3 = mock_w3
        client._contract = mock_steth_contract
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            result = await client.request_withdrawals([500_000_000_000_000_000])

        assert result.success is True
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_request_withdrawals_tx_status_zero_fails(self) -> None:
        """tx status=0 のとき request_withdrawals は失敗を返すこと。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        approve_receipt = {"status": 1}
        withdraw_receipt = {"status": 0}  # 失敗
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "cd" * 32

        mock_approve_fn = MagicMock()
        mock_approve_fn.build_transaction.return_value = {}

        mock_withdraw_fn = MagicMock()
        mock_withdraw_fn.build_transaction.return_value = {}

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.approve.return_value = mock_approve_fn

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.requestWithdrawals.return_value = mock_withdraw_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 10
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.side_effect = [
            approve_receipt,
            withdraw_receipt,
        ]
        mock_w3.eth.contract.return_value = mock_queue_contract

        client._w3 = mock_w3
        client._contract = mock_steth_contract
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            result = await client.request_withdrawals([500_000_000_000_000_000])

        assert result.success is False
        assert result.error is not None


class TestLidoClientClaimWithdrawal:
    """LidoClient.claim_withdrawal のモックテスト（チェーン接続なし）。"""

    @pytest.mark.asyncio
    async def test_claim_withdrawal_no_private_key_fails(self) -> None:
        """秘密鍵未設定で claim_withdrawal は失敗を返すこと。"""
        config = LidoConfig(sandbox=False, wallet_private_key="")
        client = LidoClient(config)
        client._initialized = True
        client._w3 = None
        client._contract = None

        result = await client.claim_withdrawal([1001])
        assert result.success is False
        assert "LIDO_WALLET_PRIVATE_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_claim_withdrawal_empty_ids_fails(self) -> None:
        """request_ids が空で claim_withdrawal は失敗を返すこと。"""
        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)
        client._initialized = True
        client._w3 = None
        client._contract = None

        result = await client.claim_withdrawal([])
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_web3_exception_returns_failure(self) -> None:
        """web3 呼び出しで例外が出たとき失敗を返すこと。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.side_effect = ValueError("invalid key")
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        # Web3 は遅延 import されるため、_w3 への side_effect で例外を発生させる
        result = await client.claim_withdrawal([1001])

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_success_with_mock(self) -> None:
        """web3 モックで claim_withdrawal 成功パスをテスト。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        claim_receipt = {"status": 1}
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "ef" * 32

        mock_claim_fn = MagicMock()
        mock_claim_fn.build_transaction.return_value = {}

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getLastCheckpointIndex.return_value.call.return_value = 100
        mock_queue_contract.functions.findCheckpointHints.return_value.call.return_value = [50]
        mock_queue_contract.functions.claimWithdrawals.return_value = mock_claim_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 5
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.return_value = claim_receipt
        mock_w3.eth.contract.return_value = mock_queue_contract

        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            result = await client.claim_withdrawal([1001])

        assert result.success is True
        assert result.tx_hash is not None
        assert result.claimed_request_ids == [1001]

    @pytest.mark.asyncio
    async def test_claim_withdrawal_tx_status_zero_fails(self) -> None:
        """tx status=0 のとき claim_withdrawal は失敗を返すこと。"""

        config = LidoConfig(sandbox=False, wallet_private_key="0x" + "aa" * 32)
        client = LidoClient(config)

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000001"

        claim_receipt = {"status": 0}  # 失敗
        fake_tx_hash_obj = MagicMock()
        fake_tx_hash_obj.hex.return_value = "0x" + "ef" * 32

        mock_claim_fn = MagicMock()
        mock_claim_fn.build_transaction.return_value = {}

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getLastCheckpointIndex.return_value.call.return_value = 100
        mock_queue_contract.functions.findCheckpointHints.return_value.call.return_value = [50]
        mock_queue_contract.functions.claimWithdrawals.return_value = mock_claim_fn

        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 5
        mock_w3.eth.gas_price = 20_000_000_000
        mock_w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash_obj
        mock_w3.eth.wait_for_transaction_receipt.return_value = claim_receipt
        mock_w3.eth.contract.return_value = mock_queue_contract

        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            result = await client.claim_withdrawal([1001])

        assert result.success is False
        assert result.error is not None


class TestLidoClientGetWithdrawalStatus:
    """LidoClient.get_withdrawal_status のモックテスト（チェーン接続なし）。"""

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_parses_response(self) -> None:
        """get_withdrawal_status がコントラクトレスポンスを正しくパースすること。"""
        import time  # noqa: PLC0415

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        now = int(time.time())
        mock_raw_statuses = [
            (
                500_000_000_000_000_000,  # amountOfStETH (0.5 ETH in Wei)
                490_000_000_000_000_000,  # amountOfShares
                "0x0000000000000000000000000000000000000001",  # owner
                now - 3600,  # timestamp
                True,  # isFinalized
                False,  # isClaimed
            )
        ]

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getWithdrawalStatus.return_value.call.return_value = (
            mock_raw_statuses
        )

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_queue_contract
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        # Web3 は遅延 import。web3.Web3.to_checksum_address を patch する
        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            statuses = await client.get_withdrawal_status([1001])

        assert len(statuses) == 1
        status = statuses[0]
        assert status.request_id == 1001
        assert type(status.amount_of_steth) is Decimal
        assert status.amount_of_steth == Decimal("500000000000000000") / Decimal(
            "1000000000000000000"
        )
        assert status.is_finalized is True
        assert status.is_claimed is False

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_raises_on_web3_error(self) -> None:
        """web3 呼び出しで例外が出たとき RuntimeError を raise すること。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getWithdrawalStatus.side_effect = RuntimeError("RPC error")

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_queue_contract
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with (
            patch("web3.Web3.to_checksum_address", return_value="0xAddress"),
            pytest.raises(RuntimeError, match="withdrawal ステータス取得失敗"),
        ):
            await client.get_withdrawal_status([1001])


class TestLidoClientReadMethods:
    """LidoClient の読み取り専用メソッドのモックテスト。"""

    @pytest.mark.asyncio
    async def test_get_steth_balance_success(self) -> None:
        """get_steth_balance が Decimal を返すこと。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.balanceOf.return_value.call.return_value = (
            1_500_000_000_000_000_000  # 1.5 ETH in Wei
        )

        client._contract = mock_steth_contract
        client._initialized = True
        client._w3 = MagicMock()

        with patch("web3.Web3.to_checksum_address", return_value="0xAddress"):
            balance = await client.get_steth_balance("0x0000000000000000000000000000000000000001")

        assert type(balance) is Decimal
        assert balance == Decimal("1500000000000000000") / Decimal("1000000000000000000")

    @pytest.mark.asyncio
    async def test_get_steth_balance_raises_on_error(self) -> None:
        """web3 エラー時に get_steth_balance は RuntimeError を raise すること。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.balanceOf.side_effect = RuntimeError("RPC error")

        client._contract = mock_steth_contract
        client._initialized = True
        client._w3 = MagicMock()

        with (
            patch("web3.Web3.to_checksum_address", return_value="0xAddress"),
            pytest.raises(RuntimeError, match="stETH 残高取得失敗"),
        ):
            await client.get_steth_balance("0xAddress")

    @pytest.mark.asyncio
    async def test_get_staking_apr_returns_35(self) -> None:
        """get_staking_apr が testnet で 3.5 を返すこと。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)
        client._initialized = True
        client._w3 = MagicMock()
        client._contract = MagicMock()

        apr = await client.get_staking_apr()
        assert type(apr) is Decimal
        assert apr == Decimal("3.5")

    @pytest.mark.asyncio
    async def test_get_steth_eth_ratio_success(self) -> None:
        """get_steth_eth_ratio が正しい比率を返すこと。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.getTotalPooledEther.return_value.call.return_value = (
            1_050_000_000_000_000_000
        )
        mock_steth_contract.functions.getTotalShares.return_value.call.return_value = (
            1_000_000_000_000_000_000
        )

        client._contract = mock_steth_contract
        client._initialized = True
        client._w3 = MagicMock()

        ratio = await client.get_steth_eth_ratio()
        assert type(ratio) is Decimal
        assert ratio == Decimal("1050000000000000000") / Decimal("1000000000000000000")

    @pytest.mark.asyncio
    async def test_get_steth_eth_ratio_zero_shares_returns_one(self) -> None:
        """total_shares が 0 のとき get_steth_eth_ratio は 1 を返すこと。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.getTotalPooledEther.return_value.call.return_value = 0
        mock_steth_contract.functions.getTotalShares.return_value.call.return_value = 0

        client._contract = mock_steth_contract
        client._initialized = True
        client._w3 = MagicMock()

        ratio = await client.get_steth_eth_ratio()
        assert ratio == Decimal("1")

    @pytest.mark.asyncio
    async def test_get_steth_eth_ratio_raises_on_error(self) -> None:
        """web3 エラー時に get_steth_eth_ratio は RuntimeError を raise すること。"""

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_steth_contract = MagicMock()
        mock_steth_contract.functions.getTotalPooledEther.side_effect = RuntimeError("RPC error")

        client._contract = mock_steth_contract
        client._initialized = True
        client._w3 = MagicMock()

        with pytest.raises(RuntimeError, match="stETH/ETH レート取得失敗"):
            await client.get_steth_eth_ratio()
