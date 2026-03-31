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


def test_missing_wallet_private_key_raises_error(mock_settings):
    """ウォレット秘密鍵が未設定の場合にエラーが発生すること。"""
    mock_settings.wallet_private_key = None

    with pytest.raises(AaveClientError, match="AAVE_WALLET_PRIVATE_KEY is required"):
        Web3AaveClient(settings=mock_settings)


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


@patch("eth_account.Account")
@patch("app.aave.client.Web3")
def test_web3_connection_error(mock_web3, mock_account, mock_settings):
    """RPC 接続失敗時のエラーハンドリング。"""
    # Web3 接続失敗をシミュレート
    mock_web3_instance = MagicMock()
    mock_web3_instance.is_connected.return_value = False
    mock_web3.return_value = mock_web3_instance
    mock_web3.HTTPProvider = MagicMock()

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
