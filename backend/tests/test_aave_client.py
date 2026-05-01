# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_client.py
"""
AaveClient のユニットテスト。

docs/14_test_strategy.md §3.4:
- FakeAaveClient (= DummyAaveClient) を使い、実 RPC には一切アクセスしない
- Web3AaveClient は unittest.mock で RPC レスポンスをモック
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.aave.client import (
    AaveClientError,
    DummyAaveClient,
    Web3AaveClient,
    make_aave_client,
)


class TestDummyAaveClient:
    def test_get_health_factor_returns_safe_value(self) -> None:
        client = DummyAaveClient()
        hf = client.get_health_factor("0x1234567890abcdef1234567890abcdef12345678")
        assert hf == Decimal("2.5")
        assert isinstance(hf, Decimal)  # float 禁止の確認

    def test_deposit_returns_dummy_hash(self) -> None:
        client = DummyAaveClient()
        result = client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0x1234567890abcdef1234567890abcdef12345678",
            private_key="0xdeadbeef",
        )
        assert isinstance(result, dict)
        assert result["tx_hash"] == "0xdummy_deposit_hash"
        assert result["dry_run"] is False

    def test_deposit_backward_compat_asset_symbol(self) -> None:
        """後方互換: deposit(asset_symbol, amount) → str"""
        client = DummyAaveClient()
        result = client.deposit("USDC", Decimal("10.5"))
        assert result == "dummy-deposit-USDC-10.5"

    def test_withdraw_returns_dummy_hash(self) -> None:
        client = DummyAaveClient()
        result = client.withdraw(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("5.0"),
            wallet_address="0x1234567890abcdef1234567890abcdef12345678",
            private_key="0xdeadbeef",
        )
        assert isinstance(result, dict)
        assert result["tx_hash"] == "0xdummy_withdraw_hash"

    def test_withdraw_backward_compat_asset_symbol(self) -> None:
        client = DummyAaveClient()
        result = client.withdraw("USDC", Decimal("5.0"))
        assert result == "dummy-withdraw-USDC-5.0"


class TestWeb3AaveClient:
    @patch("app.aave.client.Web3")
    def test_get_health_factor_normal(self, mock_web3_cls: MagicMock) -> None:
        """正常系: HF = 2.5 (= 2.5 * 1e18 raw)"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        hf_raw = int(Decimal("2.5") * Decimal(10**18))
        mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            hf_raw,
        )

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        hf = client.get_health_factor("0xabc...def")

        assert hf == Decimal("2.5")
        assert isinstance(hf, Decimal)

    @patch("app.aave.client.Web3")
    def test_get_health_factor_no_position(self, mock_web3_cls: MagicMock) -> None:
        """ポジションなし: uint256 最大値 → Decimal('inf')"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            2**256 - 1,
        )

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        hf = client.get_health_factor("0xabc...def")

        assert hf == Decimal("inf")

    @patch("app.aave.client.Web3")
    def test_get_health_factor_below_threshold(self, mock_web3_cls: MagicMock) -> None:
        """HF < 1.6 → HARD_STOP 対象の値が正しく返るか（docs/13: rule 2）"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        hf_raw = int(Decimal("1.4") * Decimal(10**18))
        mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            hf_raw,
        )

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        hf = client.get_health_factor("0xabc...def")

        assert hf < Decimal("1.6")  # HARD_STOP 閾値を下回ることを確認

    @patch("app.aave.client.Web3")
    def test_rpc_error_raises_client_error(self, mock_web3_cls: MagicMock) -> None:
        """RPC エラー → AaveClientError に変換されるか"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.side_effect = Exception(
            "connection refused"
        )

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        with pytest.raises(AaveClientError):
            client.get_health_factor("0xabc...def")

    @patch("app.aave.client.Web3")
    def test_rpc_connection_failure(self, mock_web3_cls: MagicMock) -> None:
        """初期化時に RPC 未接続 → AaveClientError"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = False
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()

        with pytest.raises(AaveClientError, match="RPC に接続できません"):
            Web3AaveClient(rpc_url="https://bad-rpc.example.com")

    @patch("app.aave.client.Web3")
    def test_deposit_dry_run(self, mock_web3_cls: MagicMock) -> None:
        """dry_run=True → tx送信なし・辞書返却"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        result = client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0xdeadbeef",
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["tx_hash"] is None
        assert result["amount"] == "10.0"
        # dry_run なので send_raw_transaction は呼ばれない
        mock_w3.eth.send_raw_transaction.assert_not_called()

    @patch("app.aave.client.Web3")
    def test_deposit_sends_tx(self, mock_web3_cls: MagicMock) -> None:
        """approve → supply の順で tx が2回送信されるか"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        # Mock token contract (ERC-20)
        mock_token = MagicMock()
        mock_token.functions.decimals.return_value.call.return_value = 6  # USDC
        mock_token.functions.approve.return_value.build_transaction.return_value = {
            "mock": "approve_tx"
        }

        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20000000000

        # sign_transaction returns object with .raw_transaction
        signed_mock = MagicMock()
        signed_mock.raw_transaction = b"signed"
        mock_w3.eth.account.sign_transaction.return_value = signed_mock

        # First send_raw_transaction call = approve, second = supply
        mock_w3.eth.send_raw_transaction.side_effect = [
            b"\xaa" * 32,  # approve hash
            b"\xbb" * 32,  # supply hash
        ]

        mock_receipt = MagicMock()
        mock_receipt.transactionHash = b"\xab" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        # Pool contract (created during __init__) uses mock_w3.eth.contract default
        # We need to separate the pool contract from the token contract.
        # During __init__, eth.contract is called once for pool.
        # During deposit, eth.contract is called once for token.
        pool_mock = MagicMock()
        pool_mock.address = "0xPoolAddress"
        pool_mock.functions.supply.return_value.build_transaction.return_value = {
            "mock": "supply_tx"
        }

        # __init__ creates pool contract; deposit creates token contract
        mock_w3.eth.contract.side_effect = [pool_mock, mock_token]

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")

        # After init, reset side_effect so deposit's eth.contract call returns mock_token
        mock_w3.eth.contract.side_effect = None
        mock_w3.eth.contract.return_value = mock_token

        # Provide a mock account (eth_account not installed in test env)
        mock_account_obj = MagicMock()
        mock_account_obj.address = "0xabc0000000000def"
        mock_account_obj.key = b"\xab" * 32
        client.account = mock_account_obj  # type: ignore[attr-defined]

        result = client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )

        assert result["dry_run"] is False
        assert result["amount"] == "10.0"
        # approve が呼ばれた
        mock_token.functions.approve.assert_called_once()
        # approve + supply の2回 tx 送信
        assert mock_w3.eth.send_raw_transaction.call_count == 2

    @patch("app.aave.client.Web3")
    def test_deposit_negative_amount_raises(self, mock_web3_cls: MagicMock) -> None:
        """amount <= 0 → ValueError"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        with pytest.raises(ValueError, match="positive"):
            client.deposit(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("-5.0"),
                wallet_address="0xabc0000000000def",
                private_key="0xdeadbeef",
            )

    @patch("app.aave.client.Web3")
    def test_deposit_zero_amount_raises(self, mock_web3_cls: MagicMock) -> None:
        """amount = 0 → ValueError"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        with pytest.raises(ValueError, match="positive"):
            client.deposit(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("0"),
                wallet_address="0xabc0000000000def",
                private_key="0xdeadbeef",
            )

    @patch("app.aave.client.Web3")
    def test_deposit_rpc_error_raises(self, mock_web3_cls: MagicMock) -> None:
        """supply失敗 → AaveClientError"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        # Mock token contract
        mock_token = MagicMock()
        mock_token.functions.decimals.return_value.call.return_value = 6
        mock_token.functions.approve.return_value.build_transaction.return_value = {}
        mock_w3.eth.contract.return_value = mock_token
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20000000000
        signed_mock = MagicMock()
        signed_mock.raw_transaction = b"signed"
        mock_w3.eth.account.sign_transaction.return_value = signed_mock
        # approve 成功・supply 失敗
        mock_w3.eth.send_raw_transaction.side_effect = [
            b"\x00" * 32,  # approve tx hash
            Exception("supply reverted"),  # supply fails
        ]
        mock_w3.eth.wait_for_transaction_receipt.return_value = MagicMock()

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        # Reset contract mock so deposit gets mock_token (not pool)
        mock_w3.eth.contract.return_value = mock_token

        # Provide a mock account (eth_account not installed in test env)
        mock_account_obj = MagicMock()
        mock_account_obj.address = "0xabc0000000000def"
        mock_account_obj.key = b"\xab" * 32
        client.account = mock_account_obj  # type: ignore[attr-defined]

        with pytest.raises(AaveClientError, match="deposit 失敗"):
            client.deposit(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("10.0"),
                wallet_address="0xabc0000000000def",
                private_key="0x" + "ab" * 32,
            )

    @patch("app.aave.client.Web3")
    def test_withdraw_dry_run(self, mock_web3_cls: MagicMock) -> None:
        """dry_run=True → tx送信なし"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        result = client.withdraw(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("5.0"),
            wallet_address="0xabc0000000000def",
            private_key="0xdeadbeef",
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["tx_hash"] is None
        mock_w3.eth.send_raw_transaction.assert_not_called()

    @patch("app.aave.client.Web3")
    def test_withdraw_hf_below_threshold_blocks(self, mock_web3_cls: MagicMock) -> None:
        """HF < 1.6 → withdrawal blocked"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        # Mock get_health_factor to return 1.4
        hf_raw = int(Decimal("1.4") * Decimal(10**18))
        mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            hf_raw,
        )

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        with pytest.raises(AaveClientError, match="HF below threshold"):
            client.withdraw(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("5.0"),
                wallet_address="0xabc0000000000def",
                private_key="0xdeadbeef",
            )
        # No tx sent
        mock_w3.eth.send_raw_transaction.assert_not_called()

    @patch("app.aave.client.Web3")
    def test_withdraw_negative_amount_raises(self, mock_web3_cls: MagicMock) -> None:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
        with pytest.raises(ValueError, match="positive"):
            client.withdraw(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("-5.0"),
                wallet_address="0xabc0000000000def",
                private_key="0xdeadbeef",
            )

    @patch("app.aave.client.Web3")
    def test_withdraw_sends_tx(self, mock_web3_cls: MagicMock) -> None:
        """HF safe → withdraw tx sent"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        # Mock HF = 2.5 (safe)
        hf_raw = int(Decimal("2.5") * Decimal(10**18))

        # Mock token contract
        mock_token = MagicMock()
        mock_token.functions.decimals.return_value.call.return_value = 6

        # Pool mock
        pool_mock = MagicMock()
        pool_mock.address = "0xPoolAddress"
        pool_mock.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            hf_raw,
        )
        pool_mock.functions.withdraw.return_value.build_transaction.return_value = {
            "mock": "withdraw_tx"
        }

        mock_w3.eth.contract.side_effect = [pool_mock, mock_token]
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20000000000

        signed_mock = MagicMock()
        signed_mock.raw_transaction = b"signed"
        mock_w3.eth.account.sign_transaction.return_value = signed_mock
        mock_w3.eth.send_raw_transaction.return_value = b"\xcc" * 32
        mock_receipt = MagicMock()
        mock_receipt.transactionHash = b"\xdd" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")

        mock_w3.eth.contract.side_effect = None
        mock_w3.eth.contract.return_value = mock_token

        mock_account_obj = MagicMock()
        mock_account_obj.address = "0xabc0000000000def"
        mock_account_obj.key = b"\xab" * 32
        client.account = mock_account_obj  # type: ignore[attr-defined]

        result = client.withdraw(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("5.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )
        assert result["dry_run"] is False
        assert result["amount"] == "5.0"
        assert mock_w3.eth.send_raw_transaction.call_count == 1

    @patch("app.aave.client.Web3")
    def test_withdraw_rpc_error_raises(self, mock_web3_cls: MagicMock) -> None:
        """withdraw tx failure → AaveClientError"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        # HF = 2.5 (safe)
        hf_raw = int(Decimal("2.5") * Decimal(10**18))

        # Pool mock captures HF; token mock handles decimals
        pool_mock = MagicMock()
        pool_mock.address = "0xPoolAddress"
        pool_mock.functions.getUserAccountData.return_value.call.return_value = (
            0,
            0,
            0,
            0,
            0,
            hf_raw,
        )

        mock_token = MagicMock()
        mock_token.functions.decimals.return_value.call.return_value = 6

        # __init__ gets pool_mock; subsequent calls (token) get mock_token
        mock_w3.eth.contract.side_effect = [pool_mock, mock_token]

        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 20000000000
        signed_mock = MagicMock()
        signed_mock.raw_transaction = b"signed"
        mock_w3.eth.account.sign_transaction.return_value = signed_mock
        mock_w3.eth.send_raw_transaction.side_effect = Exception("withdraw reverted")

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")

        # After init, reset side_effect so token contract calls use mock_token
        mock_w3.eth.contract.side_effect = None
        mock_w3.eth.contract.return_value = mock_token

        mock_account_obj = MagicMock()
        mock_account_obj.address = "0xabc0000000000def"
        mock_account_obj.key = b"\xab" * 32
        client.account = mock_account_obj  # type: ignore[attr-defined]

        with pytest.raises(AaveClientError, match="withdraw 失敗"):
            client.withdraw(
                asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                amount=Decimal("5.0"),
                wallet_address="0xabc0000000000def",
                private_key="0x" + "ab" * 32,
            )


class TestMakeAaveClient:
    def test_dummy_type(self) -> None:
        client = make_aave_client("dummy")
        assert isinstance(client, DummyAaveClient)

    def test_web3_type_missing_rpc_raises(self) -> None:
        with pytest.raises(ValueError, match="AAVE_RPC_URL"):
            make_aave_client("web3", rpc_url=None)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="不明な"):
            make_aave_client("invalid_type")


class TestWeb3AaveClientPoolAddressRequired:
    """2026-05-01 PR-A: pool_address のデフォルト None 化に対する require テスト。

    silent testnet regression (mainnet 切替後に Sepolia pool に書き込む) を防ぐため、
    Web3AaveClient.__init__ は pool_address を 引数 or AAVE_POOL_ADDRESS env から
    必須で要求する。両方欠落していれば AaveClientError を raise する。
    """

    def test_missing_pool_address_and_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """引数 pool_address なし + AAVE_POOL_ADDRESS env なし → AaveClientError。"""
        monkeypatch.delenv("AAVE_POOL_ADDRESS", raising=False)

        with pytest.raises(AaveClientError, match="AAVE_POOL_ADDRESS"):
            Web3AaveClient(rpc_url="https://mock-rpc.example.com")

    @patch("app.aave.client.Web3")
    def test_pool_address_from_env_when_argument_missing(
        self,
        mock_web3_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AAVE_POOL_ADDRESS env 設定 + 引数なし → 正常 instantiate (env 値を採用)。"""
        env_pool = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"  # Base Mainnet
        monkeypatch.setenv("AAVE_POOL_ADDRESS", env_pool)

        captured: dict[str, str] = {}

        def _to_checksum(value: str) -> str:
            captured["address"] = value
            return value

        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = _to_checksum

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")

        assert isinstance(client, Web3AaveClient)
        assert captured["address"] == env_pool

    @patch("app.aave.client.Web3")
    def test_explicit_pool_address_overrides_env(
        self,
        mock_web3_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """引数 pool_address が明示されていれば env より優先される。"""
        monkeypatch.setenv("AAVE_POOL_ADDRESS", "0xENVADDRESS")
        explicit = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"

        captured: dict[str, str] = {}

        def _to_checksum(value: str) -> str:
            captured["address"] = value
            return value

        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = _to_checksum

        Web3AaveClient(
            rpc_url="https://mock-rpc.example.com",
            pool_address=explicit,
        )

        assert captured["address"] == explicit


class TestFlashbotsProtect:
    """Flashbots Protect RPC のテスト。"""

    @patch("app.aave.client.Web3")
    def test_flashbots_rpc_creates_separate_w3_tx(self, mock_web3_cls: MagicMock) -> None:
        """Flashbots RPC 設定時に _w3_tx が _w3 と異なるインスタンスであること。"""
        mock_w3_regular = MagicMock()
        mock_w3_regular.is_connected.return_value = True
        mock_w3_flashbots = MagicMock()

        mock_web3_cls.side_effect = [mock_w3_regular, mock_w3_flashbots]
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(
            rpc_url="https://mock-rpc.example.com",
            flashbots_rpc_url="https://rpc.flashbots.net",
        )

        assert client._w3 is mock_w3_regular
        assert client._w3_tx is mock_w3_flashbots

    @patch("app.aave.client.Web3")
    def test_no_flashbots_uses_same_w3(self, mock_web3_cls: MagicMock) -> None:
        """Flashbots URL 未設定時は _w3_tx == _w3。"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")

        assert client._w3_tx is client._w3

    @patch("app.aave.client.Web3")
    def test_deposit_uses_flashbots_for_send(self, mock_web3_cls: MagicMock) -> None:
        """deposit() が Flashbots RPC 経由で send_raw_transaction を呼ぶこと。"""
        mock_w3_regular = MagicMock()
        mock_w3_regular.is_connected.return_value = True
        mock_w3_flashbots = MagicMock()

        pool_mock = MagicMock()
        pool_mock.address = "0xPoolAddress"
        pool_mock.functions.supply.return_value.build_transaction.return_value = {}

        mock_token = MagicMock()
        mock_token.functions.decimals.return_value.call.return_value = 6
        mock_token.functions.approve.return_value.build_transaction.return_value = {}

        # __init__: Web3(regular) → pool contract; Web3(flashbots)
        mock_web3_cls.side_effect = [mock_w3_regular, mock_w3_flashbots]
        mock_web3_cls.HTTPProvider = MagicMock()
        mock_web3_cls.to_checksum_address = lambda x: x

        mock_w3_regular.eth.contract.return_value = pool_mock
        mock_w3_regular.eth.get_transaction_count.return_value = 0
        mock_w3_regular.eth.gas_price = 20000000000

        signed_mock = MagicMock()
        signed_mock.raw_transaction = b"signed"
        mock_w3_regular.eth.account.sign_transaction.return_value = signed_mock

        mock_w3_flashbots.eth.send_raw_transaction.side_effect = [
            b"\xaa" * 32,
            b"\xbb" * 32,
        ]
        mock_receipt = MagicMock()
        mock_receipt.transactionHash = b"\xcc" * 32
        mock_w3_regular.eth.wait_for_transaction_receipt.return_value = mock_receipt

        client = Web3AaveClient(
            rpc_url="https://mock-rpc.example.com",
            flashbots_rpc_url="https://rpc.flashbots.net",
        )

        mock_w3_regular.eth.contract.side_effect = None
        mock_w3_regular.eth.contract.return_value = mock_token

        mock_account_obj = MagicMock()
        mock_account_obj.address = "0xabc0000000000def"
        mock_account_obj.key = b"\xab" * 32
        client.account = mock_account_obj

        result = client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )

        assert result["dry_run"] is False
        assert mock_w3_flashbots.eth.send_raw_transaction.call_count == 2
        mock_w3_regular.eth.send_raw_transaction.assert_not_called()


class TestMakeAaveClientWithChainName:
    """make_aave_client の chain_name パラメータのテスト。"""

    def test_dummy_ignores_chain_name(self) -> None:
        """dummy クライアントは chain_name を無視する。"""
        client = make_aave_client(client_type="dummy", chain_name="arbitrum")
        assert isinstance(client, DummyAaveClient)

    @patch("app.aave.client.Web3")
    @patch.dict("os.environ", {"AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com"})
    def test_web3_with_chain_name_uses_chain_config(self, mock_web3_cls: MagicMock) -> None:
        """chain_name 指定時に chains.py の設定を使用する。"""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_cls.return_value = mock_w3
        mock_web3_cls.HTTPProvider = MagicMock()

        client = make_aave_client(client_type="web3", chain_name="arbitrum")
        assert isinstance(client, Web3AaveClient)

    def test_web3_with_unknown_chain_name_raises(self) -> None:
        """未知のチェーン名で ValueError が発生する。"""
        with pytest.raises(ValueError, match="未知のチェーン名"):
            make_aave_client(client_type="web3", chain_name="unknown")


class TestMakeMultiChainClients:
    """make_multi_chain_clients のテスト。"""

    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum,optimism"})
    def test_dummy_returns_dict_of_clients(self) -> None:
        from app.aave.client import make_multi_chain_clients

        clients = make_multi_chain_clients(client_type="dummy")
        assert isinstance(clients, dict)
        assert set(clients.keys()) == {"arbitrum", "optimism"}
        for client in clients.values():
            assert isinstance(client, DummyAaveClient)

    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum"})
    def test_default_single_chain(self) -> None:
        from app.aave.client import make_multi_chain_clients

        clients = make_multi_chain_clients(client_type="dummy")
        assert len(clients) == 1
        assert "arbitrum" in clients

    @patch.dict(
        "os.environ",
        {"AAVE_ACTIVE_CHAINS": "arbitrum", "AAVE_CLIENT_TYPE": "dummy"},
    )
    def test_auto_detects_client_type_from_env(self) -> None:
        from app.aave.client import make_multi_chain_clients

        clients = make_multi_chain_clients()  # client_type=None
        assert "arbitrum" in clients
        assert isinstance(clients["arbitrum"], DummyAaveClient)
