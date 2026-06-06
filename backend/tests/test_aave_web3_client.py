# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_web3_client.py

"""
Web3AaveClient のユニットテスト。

- モックを使用したユニットテスト
- 実際の RPC 接続が必要なテストは RUN_E2E_TESTS=1 で有効化

Usage:
    # ユニットテストのみ
    pytest backend/tests/test_aave_web3_client.py -v

    # E2E テストを含む
    RUN_E2E_TESTS=1 pytest backend/tests/test_aave_web3_client.py -v
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("web3")

from app.aave.client import (
    AaveClientError,
    DummyAaveClient,
    Web3AaveClient,
    get_default_aave_client,
    make_aave_client,
)
from app.aave.config import AaveSettings

# E2E テストのスキップ条件
SKIP_E2E = os.getenv("RUN_E2E_TESTS", "0") != "1"
E2E_SKIP_REASON = "Requires RUN_E2E_TESTS=1 and Mumbai testnet setup"


@pytest.fixture
def mock_settings():
    """テスト用の AaveSettings を返す。"""
    return AaveSettings(
        network="polygon-mumbai",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("10"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url="https://rpc-mumbai.maticvigil.com",
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x5343b5bA672Ae99d627A1C87866b8E53F47Db2E6",
        pool_address="0x6C9fB0D5bD9429eb9Cd96B85B81d872281771E6B",
        pool_data_provider_address="0x8f57153F18b7273f9A814b93b31Cb3f9b035e7C2",
        wallet_private_key="0x" + "1" * 64,  # テスト用ダミー秘密鍵
        usdc_address="0x9999f7Fea5938fD3b1E26A12c3f2fb024e194f97",
    )


# ==============================================================================
# 変換ユーティリティのテスト
# ==============================================================================


def test_to_wei_conversion_usdc():
    """Decimal → Wei 変換のテスト（USDC: 6 decimals）。"""
    # Web3AaveClient のインスタンスを作らずにメソッドをテスト
    client = Web3AaveClient.__new__(Web3AaveClient)

    # 6 decimals (USDC)
    result = client._to_wei(Decimal("10.5"), 6)
    assert result == 10_500_000

    result = client._to_wei(Decimal("1.0"), 6)
    assert result == 1_000_000

    result = client._to_wei(Decimal("0.000001"), 6)
    assert result == 1


def test_to_wei_conversion_eth():
    """Decimal → Wei 変換のテスト（ETH: 18 decimals）。"""
    client = Web3AaveClient.__new__(Web3AaveClient)

    # 18 decimals (ETH)
    result = client._to_wei(Decimal("1.0"), 18)
    assert result == 10**18

    result = client._to_wei(Decimal("0.5"), 18)
    assert result == 5 * 10**17


def test_from_wei_conversion_usdc():
    """Wei → Decimal 変換のテスト（USDC: 6 decimals）。"""
    client = Web3AaveClient.__new__(Web3AaveClient)

    # 6 decimals (USDC)
    result = client._from_wei(10_500_000, 6)
    assert result == Decimal("10.5")

    result = client._from_wei(1_000_000, 6)
    assert result == Decimal("1.0")


def test_from_wei_conversion_eth():
    """Wei → Decimal 変換のテスト（ETH: 18 decimals）。"""
    client = Web3AaveClient.__new__(Web3AaveClient)

    # 18 decimals (ETH)
    result = client._from_wei(10**18, 18)
    assert result == Decimal("1.0")

    result = client._from_wei(5 * 10**17, 18)
    assert result == Decimal("0.5")


# ==============================================================================
# 設定バリデーションのテスト
# ==============================================================================


def test_missing_rpc_url_raises_error(mock_settings):
    """RPC URL が未設定の場合にエラーが発生すること。"""
    mock_settings.rpc_url = None

    with pytest.raises(AaveClientError, match="AAVE_RPC_URL is required"):
        Web3AaveClient(settings=mock_settings)


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_missing_wallet_private_key_allows_read_only_init(mock_web3, mock_account, mock_settings):
    """wallet_private_key 未設定でも read-only モードで初期化できること (v4 §14 設計)。

    Indicator Agent / shadow mode 等の eth_call のみ経路では signer 不要。
    署名 tx (supply/withdraw) 呼出時に fail-fast する。
    """
    mock_settings.wallet_private_key = None
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda addr: addr

    client = Web3AaveClient(settings=mock_settings)
    assert not hasattr(client, "account") or client.account is None


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_supply_without_wallet_fails_fast(mock_web3, mock_account, mock_settings):
    """wallet 未設定の read-only クライアントで supply を呼ぶと fail-fast すること。"""
    mock_settings.wallet_private_key = None
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda addr: addr

    client = Web3AaveClient(settings=mock_settings)
    with pytest.raises(
        AaveClientError, match="AAVE_WALLET_PRIVATE_KEY.*required for signed supply"
    ):
        client.deposit(
            asset_address="0xba50Cd2A20f6DA35D788639E581bca8d0B5d4D5f",
            amount=Decimal("1.0"),
            wallet_address="0x" + "a" * 40,
        )


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_withdraw_without_wallet_fails_fast(mock_web3, mock_account, mock_settings):
    """wallet 未設定の read-only クライアントで withdraw を呼ぶと fail-fast すること。"""
    mock_settings.wallet_private_key = None
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda addr: addr

    client = Web3AaveClient(settings=mock_settings)
    with pytest.raises(
        AaveClientError, match="AAVE_WALLET_PRIVATE_KEY.*required for signed withdraw"
    ):
        client.withdraw(
            asset_address="0xba50Cd2A20f6DA35D788639E581bca8d0B5d4D5f",
            amount=Decimal("1.0"),
            wallet_address="0x" + "a" * 40,
        )


def test_missing_pool_address_raises_error(mock_settings):
    """Pool アドレスが未設定の場合にエラーが発生すること。"""
    mock_settings.pool_address = None

    with pytest.raises(AaveClientError, match="AAVE_POOL_ADDRESS is required"):
        Web3AaveClient(settings=mock_settings)


def test_missing_usdc_address_raises_error(mock_settings):
    """USDC アドレスが未設定の場合にエラーが発生すること。"""
    mock_settings.usdc_address = None

    with pytest.raises(AaveClientError, match="AAVE_USDC_ADDRESS is required"):
        Web3AaveClient(settings=mock_settings)


# ==============================================================================
# RPC 接続のテスト（モック）
# ==============================================================================


@patch("app.aave.rpc_provider.RPCProvider")
@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_web3_connection_error(mock_web3, mock_account, mock_rpc_provider_cls, mock_settings):
    """RPC 接続失敗時のエラーハンドリング。

    接続判定は RPCProvider.get_web3() に一本化されており、ConnectionError を投げる
    ケースのみが「RPC に接続できません」エラーに繋がる。`Web3.is_connected()` は
    web3.py 7.x で `web3_clientVersion` RPC を呼ぶ仕様となり、Base Sepolia 等の一部
    public RPC で false positive を返すため、二段目のチェックは削除済み。
    """
    mock_web3.HTTPProvider = MagicMock()

    mock_provider_instance = MagicMock()
    mock_provider_instance.get_web3.side_effect = ConnectionError("All RPC endpoints unavailable")
    mock_rpc_provider_cls.return_value = mock_provider_instance

    with pytest.raises(AaveClientError, match="RPC に接続できません"):
        Web3AaveClient(settings=mock_settings)


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_web3_client_initialization_success(mock_web3, mock_account, mock_settings):
    """Web3AaveClient が正常に初期化できること（モック）。"""
    # Web3 接続成功をシミュレート
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    # Account モック
    mock_account_instance = MagicMock()
    mock_account_instance.address = "0x1234567890abcdef1234567890abcdef12345678"
    mock_account.from_key.return_value = mock_account_instance

    client = Web3AaveClient(settings=mock_settings)

    assert client.w3.is_connected()
    assert client.account.address == "0x1234567890abcdef1234567890abcdef12345678"


# ==============================================================================
# get_health_factor のテスト（モック）
# ==============================================================================


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_get_health_factor_returns_value(mock_web3, mock_account, mock_settings):
    """ヘルスファクターが正常に取得できること（モック）。"""
    # Web3 モック
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    # Account モック
    mock_account_instance = MagicMock()
    mock_account_instance.address = "0x1234"
    mock_account.from_key.return_value = mock_account_instance

    # Pool コントラクトモック
    mock_pool = MagicMock()
    # healthFactor = 2.0 (1e18 スケール)
    mock_pool.functions.getUserAccountData.return_value.call.return_value = (
        100000000,  # totalCollateralBase
        50000000,  # totalDebtBase
        50000000,  # availableBorrowsBase
        8000,  # currentLiquidationThreshold
        7500,  # ltv
        2 * 10**18,  # healthFactor = 2.0
    )
    mock_web3_instance.eth.contract.return_value = mock_pool

    client = Web3AaveClient(settings=mock_settings)
    hf = client.get_health_factor()

    assert hf == Decimal("2.0")


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_get_health_factor_returns_none_for_no_debt(mock_web3, mock_account, mock_settings):
    """借入がない場合に Decimal('inf') が返ること（モック）。"""
    # Web3 モック
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    # Account モック
    mock_account_instance = MagicMock()
    mock_account_instance.address = "0x1234"
    mock_account.from_key.return_value = mock_account_instance

    # Pool コントラクトモック（healthFactor = 0, totalDebtBase = 0 は借入なし）
    mock_pool = MagicMock()
    mock_pool.functions.getUserAccountData.return_value.call.return_value = (
        0,
        0,
        0,
        0,
        0,
        0,  # totalDebtBase=0, healthFactor = 0
    )
    mock_web3_instance.eth.contract.return_value = mock_pool

    client = Web3AaveClient(settings=mock_settings)
    hf = client.get_health_factor()

    assert hf == Decimal("inf")


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_get_health_factor_returns_zero_for_critical_debt(mock_web3, mock_account, mock_settings):
    """借入ありで HF=0 の場合に Decimal('0') が返ること（清算寸前の危険状態）。"""
    # Web3 モック
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = True
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    # Account モック
    mock_account_instance = MagicMock()
    mock_account_instance.address = "0x1234"
    mock_account.from_key.return_value = mock_account_instance

    # Pool コントラクトモック（healthFactor = 0, totalDebtBase > 0 は清算寸前）
    mock_pool = MagicMock()
    mock_pool.functions.getUserAccountData.return_value.call.return_value = (
        100000000,  # totalCollateralBase
        50000000,  # totalDebtBase > 0 (債務あり)
        0,  # availableBorrowsBase
        8000,  # currentLiquidationThreshold
        7500,  # ltv
        0,  # healthFactor = 0 (清算寸前)
    )
    mock_web3_instance.eth.contract.return_value = mock_pool

    client = Web3AaveClient(settings=mock_settings)
    hf = client.get_health_factor()

    # 借入ありで HF=0 の場合は Decimal('0') を返す（fail-closed 原則）
    assert hf == Decimal("0")


# ==============================================================================
# get_default_aave_client のテスト
# ==============================================================================


def test_get_default_aave_client_dummy():
    """AAVE_CLIENT_TYPE=dummy の場合に DummyAaveClient が返ること。"""
    import os

    os.environ["AAVE_CLIENT_TYPE"] = "dummy"
    try:
        client = get_default_aave_client()
        assert isinstance(client, DummyAaveClient)
    finally:
        del os.environ["AAVE_CLIENT_TYPE"]


def test_get_default_aave_client_auto_dev():
    """APP_ENV=dev の場合に DummyAaveClient が返ること。"""
    import os

    # AAVE_CLIENT_TYPE をクリア
    if "AAVE_CLIENT_TYPE" in os.environ:
        del os.environ["AAVE_CLIENT_TYPE"]

    os.environ["APP_ENV"] = "dev"
    try:
        client = get_default_aave_client()
        assert isinstance(client, DummyAaveClient)
    finally:
        if "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


# ==============================================================================
# DummyAaveClient のテスト
# ==============================================================================


def test_dummy_client_health_factor():
    """DummyAaveClient が固定のヘルスファクターを返すこと。"""
    settings = AaveSettings(
        network="test",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0",
    )
    client = DummyAaveClient(settings=settings)

    assert client.get_health_factor() == Decimal("2.5")


def test_dummy_client_deposit():
    """DummyAaveClient の deposit がダミー tx hash を返すこと。"""
    settings = AaveSettings(
        network="test",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0",
    )
    client = DummyAaveClient(settings=settings)

    tx_hash = client.deposit("USDC", Decimal("10.5"))
    assert tx_hash == "dummy-deposit-USDC-10.5"


def test_dummy_client_withdraw():
    """DummyAaveClient の withdraw がダミー tx hash を返すこと。"""
    settings = AaveSettings(
        network="test",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0",
    )
    client = DummyAaveClient(settings=settings)

    tx_hash = client.withdraw("USDC", Decimal("5.0"))
    assert tx_hash == "dummy-withdraw-USDC-5.0"


# ==============================================================================
# Arbitrum アドレス定数のテスト
# ==============================================================================


def test_arbitrum_pool_address_format():
    """Arbitrum Pool アドレスが正しい形式であること。"""
    from app.aave.client import _POOL_ADDRESS_ARBITRUM

    assert _POOL_ADDRESS_ARBITRUM.startswith("0x")
    assert len(_POOL_ADDRESS_ARBITRUM) == 42


def test_arbitrum_usdc_address_format():
    """Arbitrum USDC アドレスが正しい形式であること。"""
    from app.aave.client import _USDC_ADDRESS_ARBITRUM

    assert _USDC_ADDRESS_ARBITRUM.startswith("0x")
    assert len(_USDC_ADDRESS_ARBITRUM) == 42


def test_make_aave_client_with_network_arbitrum():
    """make_aave_client(network='arbitrum') で正しい pool address が使われること。"""
    with patch("app.aave.client.Web3") as mock_web3:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3.return_value = mock_w3
        mock_web3.HTTPProvider = MagicMock()
        mock_web3.to_checksum_address = lambda x: x

        client = make_aave_client(
            "web3",
            rpc_url="https://arb-mainnet.example.com",
            network="arbitrum",
        )
        assert isinstance(client, Web3AaveClient)


# ==============================================================================
# E2E テスト（Mumbai テストネット接続が必要）
# ==============================================================================
#
# 有効化方法:
#   RUN_E2E_TESTS=1 pytest backend/tests/test_aave_web3_client.py -v
#
# 前提条件:
#   - Mumbai RPC エンドポイント
#   - テストウォレット（秘密鍵）
#   - Mumbai MATIC（ガス代）
#   - Test USDC（deposit/withdraw テスト用）
#
# セットアップ:
#   bash scripts/setup_mumbai_test.sh
#
# ==============================================================================


@pytest.mark.skipif(SKIP_E2E, reason=E2E_SKIP_REASON)
@pytest.mark.e2e
def test_web3_client_initialization_live(mock_settings):
    """Web3AaveClient が実際の RPC に接続できること。"""
    client = Web3AaveClient(settings=mock_settings)
    assert client.w3.is_connected()
    assert client.account.address is not None


@pytest.mark.skipif(SKIP_E2E, reason=E2E_SKIP_REASON)
@pytest.mark.e2e
def test_get_health_factor_live(mock_settings):
    """ヘルスファクター取得（ライブテスト）。"""
    client = Web3AaveClient(settings=mock_settings)
    hf = client.get_health_factor()
    # ポジションがない場合は None が返る
    assert hf is None or hf > Decimal("0")


@pytest.mark.skipif(SKIP_E2E, reason=E2E_SKIP_REASON)
@pytest.mark.e2e
def test_deposit_live(mock_settings):
    """Deposit のライブテスト（少額）。"""
    client = Web3AaveClient(settings=mock_settings)
    tx_hash = client.deposit("USDC", Decimal("0.1"))
    assert tx_hash.startswith("0x")
    assert len(tx_hash) == 66  # 0x + 64 hex chars


@pytest.mark.skipif(SKIP_E2E, reason=E2E_SKIP_REASON)
@pytest.mark.e2e
def test_withdraw_live(mock_settings):
    """Withdraw のライブテスト。"""
    client = Web3AaveClient(settings=mock_settings)
    tx_hash = client.withdraw("USDC", Decimal("0.1"))
    assert tx_hash.startswith("0x")
    assert len(tx_hash) == 66


# ==============================================================================
# 欠陥修正の回帰テスト: wallet_address 伝播 (2026-05-31 RCA)
#
# 背景:
#   backward-compat 分岐で `else: raise AaveClientError("No wallet configured")` が
#   wallet_address 渡し済みの正常ケースで誤発火していた。
#   FakeAaveClient を使う上位テストでは検出されず、Web3AaveClient 固有のバグ。
# ==============================================================================


def _make_mocked_web3_client(mock_web3, mock_rpc_provider_cls, mock_settings):
    """テスト用 Web3AaveClient をモックで構築するヘルパー。"""
    from eth_account import Account as EthAccount

    # サーバー用ダミーアカウント (AAVE_WALLET_PRIVATE_KEY)
    server_key = "0x" + "a" * 64
    server_account = EthAccount.from_key(server_key)
    mock_settings.wallet_private_key = server_key

    mock_rpc_provider_instance = MagicMock()
    mock_w3 = MagicMock()
    mock_w3.eth.chain_id = 84532
    mock_w3.eth.gas_price = 1_000_000_000
    mock_rpc_provider_instance.get_web3.return_value = mock_w3
    mock_rpc_provider_cls.return_value = mock_rpc_provider_instance

    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    # Pool contract mock (eth.contract の返値)
    mock_pool = MagicMock()
    mock_pool.address = "0xPOOL"

    # decimals() は整数 6 を返す (USDC)
    mock_pool.functions.decimals.return_value.call.return_value = 6

    # getUserAccountData: HF=2.0, debt=0 (HF チェックを通過させる)
    mock_pool.functions.getUserAccountData.return_value.call.return_value = (
        0,
        0,
        0,
        0,
        0,
        int(2e18),
    )

    # approve / supply / withdraw の build_transaction
    mock_pool.functions.approve.return_value.build_transaction.return_value = {
        "from": "",
        "nonce": 0,
    }
    mock_pool.functions.supply.return_value.build_transaction.return_value = {
        "from": "",
        "nonce": 0,
    }
    mock_pool.functions.withdraw.return_value.build_transaction.return_value = {
        "from": "",
        "nonce": 0,
    }

    # eth.contract → 常に mock_pool を返す
    mock_w3.eth.contract.return_value = mock_pool

    # send_raw_transaction / wait / nonce / sign
    dummy_receipt = {"transactionHash": b"\xab" * 32, "status": 1, "blockNumber": 1}
    mock_w3.eth.wait_for_transaction_receipt.return_value = dummy_receipt
    mock_w3.eth.send_raw_transaction.return_value = b"\xab" * 32
    mock_w3.eth.get_transaction_count.return_value = 0
    mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"\x00")

    return Web3AaveClient(settings=mock_settings), mock_pool, server_account


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_deposit_with_explicit_wallet_address_does_not_raise(
    mock_web3, mock_rpc_provider_cls, mock_settings
):
    """
    欠陥1 回帰: deposit() に wallet_address を渡したとき AaveClientError が出ないこと。

    backward-compat 分岐の `else: raise` が wallet_address 渡し済みのケースで
    誤発火していたバグの回帰テスト。
    """
    partner_wallet = "0x" + "2" * 40

    client, mock_pool, _server = _make_mocked_web3_client(
        mock_web3, mock_rpc_provider_cls, mock_settings
    )

    # asset_address="USDC" (symbol as positional, backward-compat 分岐) + wallet_address 指定
    # 修正前はここで AaveClientError("No wallet configured") が raise された
    result = client.deposit(
        asset_address="USDC",
        amount=Decimal("1.0"),
        wallet_address=partner_wallet,
    )
    assert result is not None


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_deposit_supply_uses_partner_wallet_as_on_behalf_of(
    mock_web3, mock_rpc_provider_cls, mock_settings
):
    """
    欠陥1 回帰: deposit() が Pool.supply の onBehalfOf に渡した wallet_address を使うこと。

    AaveService.execute_rebalance が wallet_address=partner を渡したとき、
    Pool.supply(asset, amount, onBehalfOf=partner, 0) と呼ばれることを検証する。
    サーバーウォレット (self.account.address) が onBehalfOf に入らないことも確認。
    """
    partner_wallet = "0x" + "2" * 40

    client, mock_pool, server_account = _make_mocked_web3_client(
        mock_web3, mock_rpc_provider_cls, mock_settings
    )

    client.deposit(
        asset_address="USDC",
        amount=Decimal("1.0"),
        wallet_address=partner_wallet,
    )

    # Pool.supply が呼ばれた引数を確認
    supply_call_args = mock_pool.functions.supply.call_args
    assert supply_call_args is not None, "Pool.supply が呼ばれていない"
    positional = supply_call_args.args  # (asset, amount_wei, onBehalfOf, referralCode)
    on_behalf_of = positional[2]
    assert on_behalf_of == partner_wallet, (
        f"onBehalfOf={on_behalf_of} はパートナー wallet であるべき (={partner_wallet})"
    )
    # サーバーウォレットが onBehalfOf に入っていないこと
    assert on_behalf_of != server_account.address, "サーバーウォレットが onBehalfOf に入っている"


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_deposit_without_wallet_address_falls_back_to_server_wallet(
    mock_web3, mock_rpc_provider_cls, mock_settings
):
    """
    wallet_address 未指定時は後方互換でサーバーウォレットにフォールバックすること。

    non-custodial 移行後は本来呼ばれないが、既存の custodial フローが壊れていないことを確認。
    """
    client, mock_pool, server_account = _make_mocked_web3_client(
        mock_web3, mock_rpc_provider_cls, mock_settings
    )

    # wallet_address を渡さない (backward-compat パス)
    result = client.deposit(asset_address="USDC", amount=Decimal("1.0"))
    assert result is not None

    supply_call_args = mock_pool.functions.supply.call_args
    on_behalf_of = supply_call_args.args[2]
    # サーバーウォレットが使われること
    assert on_behalf_of == server_account.address


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_withdraw_with_explicit_wallet_address_does_not_raise(
    mock_web3, mock_rpc_provider_cls, mock_settings
):
    """
    欠陥1 回帰 (withdraw): wallet_address を渡したとき AaveClientError が出ないこと。
    """
    partner_wallet = "0x" + "2" * 40

    client, mock_pool, _server = _make_mocked_web3_client(
        mock_web3, mock_rpc_provider_cls, mock_settings
    )
    # HF check のため getUserAccountData が呼ばれる — inf を返す設定済み (no debt)

    result = client.withdraw(
        asset_address="USDC",
        amount=Decimal("1.0"),
        wallet_address=partner_wallet,
    )
    assert result is not None


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_withdraw_uses_partner_wallet_as_to(mock_web3, mock_rpc_provider_cls, mock_settings):
    """
    欠陥1 回帰 (withdraw): Pool.withdraw の to に渡した wallet_address が使われること。
    """
    partner_wallet = "0x" + "2" * 40

    client, mock_pool, server_account = _make_mocked_web3_client(
        mock_web3, mock_rpc_provider_cls, mock_settings
    )

    client.withdraw(
        asset_address="USDC",
        amount=Decimal("1.0"),
        wallet_address=partner_wallet,
    )

    withdraw_call_args = mock_pool.functions.withdraw.call_args
    assert withdraw_call_args is not None, "Pool.withdraw が呼ばれていない"
    positional = withdraw_call_args.args  # (asset, amount_wei, to)
    to_address = positional[2]
    assert to_address == partner_wallet, (
        f"to={to_address} はパートナー wallet であるべき (={partner_wallet})"
    )
    assert to_address != server_account.address


# ==============================================================================
# 回帰テスト: マルチチェーン client の token_addresses 配線
# (2026-06-02 launch ブロッカー: make_aave_client(chain_name=...) が
#  chain_config.tokens を Web3AaveClient に渡さず、build_deposit_txs /
#  build_withdraw_tx が "Unknown asset" で 500 になっていた)
# ==============================================================================

_BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_BASE_SEPOLIA_USDC = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"


def _mock_multichain_client(mock_web3, mock_rpc_provider_cls, chain_name):
    """settings 無し（マルチチェーン経路）で make_aave_client を実行するヘルパー。"""
    mock_rpc_provider_instance = MagicMock()
    mock_w3 = MagicMock()
    mock_w3.eth.chain_id = 8453 if chain_name == "base" else 84532
    mock_rpc_provider_instance.get_web3.return_value = mock_w3
    mock_rpc_provider_cls.return_value = mock_rpc_provider_instance

    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x

    mock_pool = MagicMock()
    mock_pool.address = "0xPOOL"
    mock_pool.functions.decimals.return_value.call.return_value = 6
    # web3 v7: Contract.encode_abi (encodeABI は v7 で廃止)
    mock_pool.encode_abi.return_value = "0xdeadbeef"
    mock_w3.eth.contract.return_value = mock_pool

    client = make_aave_client(client_type="web3", chain_name=chain_name)
    return client, mock_pool


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_make_aave_client_base_wires_token_addresses(mock_web3, mock_rpc_provider_cls):
    """
    回帰: make_aave_client(chain_name="base") が chain_config.tokens を client に配線し、
    token_addresses 属性が存在して USDC が解決できること。
    (配線漏れだと hasattr=False → build_deposit_txs が "Unknown asset")
    """
    with patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "https://base.example"}):
        client, _pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base")

    assert hasattr(client, "token_addresses"), "token_addresses 未配線 (Unknown asset の原因)"
    assert client.token_addresses.get("USDC") == _BASE_USDC
    # chain_config.tokens の他トークンも配線される
    assert "WETH" in client.token_addresses
    # WBTC / USDT / DAI は Base Aave V3 非上場のため chain map から除外済み (347f7afb)
    assert "WBTC" not in client.token_addresses


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_make_aave_client_base_sepolia_wires_token_addresses(mock_web3, mock_rpc_provider_cls):
    """回帰: base_sepolia でも token_addresses が配線される (staging proof 経路)。"""
    with patch.dict(os.environ, {"ALCHEMY_RPC_URL_BASE_SEPOLIA": "https://sepolia.base.org"}):
        client, _pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base_sepolia")

    assert hasattr(client, "token_addresses")
    assert client.token_addresses.get("USDC") == _BASE_SEPOLIA_USDC


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_build_deposit_txs_multichain_no_unknown_asset(mock_web3, mock_rpc_provider_cls):
    """
    回帰 (本丸): マルチチェーン経路で生成した client の build_deposit_txs("USDC") が
    "Unknown asset" を投げず、approve_tx / supply_tx を返すこと。
    onBehalfOf/from は partner wallet (build_deposit_txs は checksum_wallet を from に使う)。
    """
    partner_wallet = "0x" + "d" * 40
    with patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "https://base.example"}):
        client, _pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base")

        result = client.build_deposit_txs(
            asset_symbol="USDC",
            amount=Decimal("1.0"),
            wallet_address=partner_wallet,
        )

    assert "approve_tx" in result and "supply_tx" in result
    # non-custodial: 両 tx の from は partner wallet
    assert result["approve_tx"]["from"] == partner_wallet
    assert result["supply_tx"]["from"] == partner_wallet


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_build_withdraw_tx_multichain_no_unknown_asset(mock_web3, mock_rpc_provider_cls):
    """回帰 (withdraw): マルチチェーン経路で build_withdraw_tx も Unknown asset を出さない。"""
    partner_wallet = "0x" + "d" * 40
    with patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "https://base.example"}):
        client, _pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base")

        result = client.build_withdraw_tx(
            asset_symbol="USDC",
            amount=Decimal("1.0"),
            wallet_address=partner_wallet,
        )

    assert "withdraw_tx" in result
    assert result["withdraw_tx"]["from"] == partner_wallet


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_web3client_token_addresses_param_sets_attr(mock_web3, mock_rpc_provider_cls):
    """
    回帰: Web3AaveClient(settings=None, token_addresses=...) で token_addresses が設定され、
    checksum 化されること。
    """
    mock_rpc_provider_instance = MagicMock()
    mock_rpc_provider_instance.get_web3.return_value = MagicMock()
    mock_rpc_provider_cls.return_value = mock_rpc_provider_instance
    mock_web3.HTTPProvider = MagicMock()
    mock_web3.to_checksum_address = lambda x: x.upper()  # checksum 化が呼ばれることを確認

    client = Web3AaveClient(
        rpc_url="https://base.example",
        pool_address="0xpool",
        token_addresses={"USDC": _BASE_USDC},
    )

    assert hasattr(client, "token_addresses")
    assert client.token_addresses["USDC"] == _BASE_USDC.upper()


# ==============================================================================
# 回帰テスト: web3.py v7 API (encode_abi) — encodeABI は v7 で廃止
# (2026-06-02 launch ブロッカー: build_deposit_txs/build_withdraw_tx が
#  廃止 API encodeABI を使い 'Contract' object has no attribute 'encodeABI' で 500。
#  #500 の mock は MagicMock が任意メソッドに応答するため drift を検出できなかった)
# ==============================================================================

_APPROVE_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def test_web3_v7_contract_api_pin():
    """
    版ピン: インストール済み web3 の Contract は encode_abi を持ち encodeABI を持たない。
    web3 メジャー更新 / ダウングレードで API drift したら検出する。
    """
    from web3 import Web3

    w3 = Web3()  # provider 不要（ABI encode はオフライン）
    contract = w3.eth.contract(abi=_APPROVE_ABI, address="0x" + "1" * 40)

    assert hasattr(contract, "encode_abi"), "web3 v7 の encode_abi が無い (API drift)"
    assert not hasattr(contract, "encodeABI"), "encodeABI は v7 で廃止のはず"

    # 位置引数 + args= で encode できること（fn_name= は v7 で廃止）
    data = contract.encode_abi("approve", args=["0x" + "2" * 40, 1000])
    assert data.startswith("0x")


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_build_deposit_txs_uses_encode_abi_v7_api(mock_web3, mock_rpc_provider_cls):
    """
    回帰: build_deposit_txs が v7 API encode_abi を呼び、廃止 API encodeABI を呼ばないこと。
    (旧コードに戻ると encode_abi が呼ばれず encodeABI が呼ばれてこのテストが落ちる)
    """
    partner_wallet = "0x" + "d" * 40
    with patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "https://base.example"}):
        client, mock_pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base")
        client.build_deposit_txs(
            asset_symbol="USDC", amount=Decimal("1.0"), wallet_address=partner_wallet
        )

    assert mock_pool.encode_abi.called, "v7 API encode_abi が呼ばれていない"
    assert not mock_pool.encodeABI.called, "廃止 API encodeABI を呼んでいる (v7 で 500)"


@patch("app.aave.rpc_provider.RPCProvider")
@patch("app.aave.client.Web3")
def test_build_withdraw_tx_uses_encode_abi_v7_api(mock_web3, mock_rpc_provider_cls):
    """回帰 (withdraw): build_withdraw_tx も v7 API encode_abi を使うこと。"""
    partner_wallet = "0x" + "d" * 40
    with patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "https://base.example"}):
        client, mock_pool = _mock_multichain_client(mock_web3, mock_rpc_provider_cls, "base")
        client.build_withdraw_tx(
            asset_symbol="USDC", amount=Decimal("1.0"), wallet_address=partner_wallet
        )

    assert mock_pool.encode_abi.called
    assert not mock_pool.encodeABI.called
