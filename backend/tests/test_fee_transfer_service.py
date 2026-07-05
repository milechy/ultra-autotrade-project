# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_fee_transfer_service.py
"""FeeTransferService ユニットテスト (F-S6: 設計A / fee_transfer_service)。

FeeTransferConfig (OPERATOR_FEE_WALLET_ADDRESS/_KEY) ベースの operator wallet 送金経路。
on-chain 呼び出しはすべて mock。実際の RPC は使わない。
staging 実 tx は scripts/test_fee_transfer_staging.py で別途実施。

注: 設計B (transfer_service / allowance_service, FEE_RECIPIENT_ADDRESS + AAVE_WALLET_PRIVATE_KEY
流用) は 2026-07-05 に削除済み。設計Aに統一。
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.fees.fee_transfer_service import (
    FeeTransferConfig,
    FeeTransferService,
    is_fee_transfer_enabled,
)

# app import 用の最小 env 初期化
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-fee-transfer")
os.environ.setdefault("ALCHEMY_RPC_URL_BASE_SEPOLIA", "https://fake-rpc.example.com")
os.environ.setdefault("AAVE_NETWORK", "base_sepolia")

# ---------------------------------------------------------------------------
# Fixtures (F-S6: fee_transfer_service)
# ---------------------------------------------------------------------------

BASE_SEPOLIA_CFG = FeeTransferConfig(
    enabled=True,
    operator_wallet_address="0xOperator000000000000000000000000000000001",
    operator_wallet_key="0xdeadbeef" + "00" * 28,
    rpc_url="https://base-sepolia.example.com",
    data_provider_address="0xBc9f5b7E248451CdD7cA54e717a2BFe1F32b566b",
    usdc_address="0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f",
    chain_id=84532,
)

DISABLED_CFG = FeeTransferConfig(
    enabled=False,
    operator_wallet_address="",
    operator_wallet_key="",
    rpc_url="",
    data_provider_address="",
    usdc_address="",
    chain_id=84532,
)

USER_WALLET = "0xUserWallet00000000000000000000000000000001"


# ---------------------------------------------------------------------------
# is_fee_transfer_enabled
# ---------------------------------------------------------------------------


def test_is_fee_transfer_enabled_default_false():
    """デフォルト (未設定) では False。"""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FEE_TRANSFER_ENABLED", None)
        assert is_fee_transfer_enabled() is False


def test_is_fee_transfer_enabled_true():
    with patch.dict(os.environ, {"FEE_TRANSFER_ENABLED": "true"}):
        assert is_fee_transfer_enabled() is True


def test_is_fee_transfer_enabled_uppercase():
    with patch.dict(os.environ, {"FEE_TRANSFER_ENABLED": "TRUE"}):
        assert is_fee_transfer_enabled() is True


# ---------------------------------------------------------------------------
# transfer_fee: disabled / skipped ケース
# ---------------------------------------------------------------------------


def test_transfer_fee_disabled_returns_skipped():
    """FEE_TRANSFER_ENABLED=false → status='skipped'、送金なし。"""
    svc = FeeTransferService(DISABLED_CFG)
    result = svc.transfer_fee(
        user_id=1,
        user_wallet=USER_WALLET,
        fee_amount_jpy=Decimal("10000"),
        subscription_amount_jpy=Decimal("5000"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("150"),
    )
    assert result.status == "skipped"
    assert result.tx_hash is None
    assert result.fee_usd == Decimal("0")


def test_transfer_fee_no_wallet_returns_skipped():
    """user_wallet が空の場合 → status='skipped'。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    result = svc.transfer_fee(
        user_id=2,
        user_wallet="",
        fee_amount_jpy=Decimal("10000"),
        subscription_amount_jpy=Decimal("0"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("150"),
    )
    assert result.status == "skipped"


def test_transfer_fee_low_fee_returns_low_fee():
    """fee_usd < MIN_FEE_USD → status='low_fee'。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    # 1円 / 150 = 0.0067 USD だが、0.001 USD になるよう rate を大きく
    result = svc.transfer_fee(
        user_id=3,
        user_wallet=USER_WALLET,
        fee_amount_jpy=Decimal("1"),  # 1 JPY
        subscription_amount_jpy=Decimal("0"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("10000"),  # 1 JPY = 0.0001 USD → below MIN_FEE_USD
    )
    assert result.status == "low_fee"
    assert result.tx_hash is None


def test_transfer_fee_invalid_rate_returns_failed():
    """usd_jpy_rate=0 → status='failed'。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    result = svc.transfer_fee(
        user_id=4,
        user_wallet=USER_WALLET,
        fee_amount_jpy=Decimal("10000"),
        subscription_amount_jpy=Decimal("0"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("0"),
    )
    assert result.status == "failed"
    assert "usd_jpy_rate" in (result.error or "")


def test_transfer_fee_no_operator_key_returns_failed():
    """OPERATOR_FEE_WALLET_KEY 未設定 → status='failed'。"""
    cfg = FeeTransferConfig(
        enabled=True,
        operator_wallet_address="0xOperator",
        operator_wallet_key="",  # 空
        rpc_url="https://rpc",
        data_provider_address="0xDP",
        usdc_address="0xUSDC",
        chain_id=84532,
    )
    svc = FeeTransferService(cfg)
    result = svc.transfer_fee(
        user_id=5,
        user_wallet=USER_WALLET,
        fee_amount_jpy=Decimal("10000"),
        subscription_amount_jpy=Decimal("0"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("150"),
    )
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# transfer_fee: mock Web3 — sent ケース
# ---------------------------------------------------------------------------


def _make_w3_mock(
    decimals: int = 6,
    allowance: int = 10_000_000,  # 10 USDC
    tx_receipt_status: int = 1,
    atoken_address: str = "0xAToken000000000000000000000000000000000001",
) -> MagicMock:
    """Web3 モックを返す。"""
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda x: x

    # Pool Data Provider mock
    dp_contract = MagicMock()
    dp_contract.functions.getReserveTokensAddresses.return_value.call.return_value = (
        atoken_address,
        "0xSDebt",
        "0xVDebt",
    )

    # aToken contract mock
    atoken_contract = MagicMock()
    atoken_contract.functions.decimals.return_value.call.return_value = decimals
    atoken_contract.functions.allowance.return_value.call.return_value = allowance

    def contract_factory(address, abi):
        if "getReserveTokensAddresses" in str(abi):
            return dp_contract
        return atoken_contract

    w3.eth.contract.side_effect = contract_factory

    # tx signing / sending
    account = MagicMock()
    account.address = "0xOperator000000000000000000000000000000001"
    w3.eth.account.from_key.return_value = account
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1000000000

    signed_tx = MagicMock()
    signed_tx.raw_transaction = b"\x00" * 100
    w3.eth.account.sign_transaction.return_value = signed_tx

    tx_hash = MagicMock()
    tx_hash.hex.return_value = "0xdeadbeef" + "00" * 28
    w3.eth.send_raw_transaction.return_value = tx_hash

    receipt = MagicMock()
    receipt.status = tx_receipt_status
    w3.eth.wait_for_transaction_receipt.return_value = receipt

    # build_transaction on function mock
    atoken_contract.functions.transferFrom.return_value.build_transaction.return_value = {
        "to": atoken_address,
        "data": "0x",
        "from": account.address,
        "nonce": 0,
        "chainId": 84532,
        "gas": 100000,
        "gasPrice": 1000000000,
    }

    return w3


def test_transfer_fee_sent_success():
    """allowance 十分 + tx success → status='sent', tx_hash 設定。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = _make_w3_mock(allowance=100_000_000)  # 100 USDC allowance

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        result = svc.transfer_fee(
            user_id=10,
            user_wallet=USER_WALLET,
            fee_amount_jpy=Decimal("1500"),  # 1500 JPY = 10 USD @ 150
            subscription_amount_jpy=Decimal("0"),
            yield_excess_jpy=Decimal("0"),
            usd_jpy_rate=Decimal("150"),
        )

    assert result.status == "sent"
    assert result.tx_hash is not None
    assert result.fee_usd == Decimal("10.000000")
    assert result.atoken_units == 10_000_000  # 10 USDC × 10^6


def test_transfer_fee_no_allowance():
    """allowance 不足 → status='no_allowance'、送金しない。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = _make_w3_mock(allowance=0)  # allowance ゼロ

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        result = svc.transfer_fee(
            user_id=11,
            user_wallet=USER_WALLET,
            fee_amount_jpy=Decimal("1500"),
            subscription_amount_jpy=Decimal("0"),
            yield_excess_jpy=Decimal("0"),
            usd_jpy_rate=Decimal("150"),
        )

    assert result.status == "no_allowance"
    assert result.tx_hash is None


def test_transfer_fee_tx_reverted():
    """tx status=0 (revert) → status='failed'。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = _make_w3_mock(allowance=100_000_000, tx_receipt_status=0)

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        result = svc.transfer_fee(
            user_id=12,
            user_wallet=USER_WALLET,
            fee_amount_jpy=Decimal("1500"),
            subscription_amount_jpy=Decimal("0"),
            yield_excess_jpy=Decimal("0"),
            usd_jpy_rate=Decimal("150"),
        )

    assert result.status == "failed"
    assert "reverted" in (result.error or "")


def test_transfer_fee_web3_exception():
    """Web3 例外 → status='failed'。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = MagicMock()
    mock_w3.to_checksum_address.side_effect = lambda x: x
    mock_w3.eth.contract.side_effect = RuntimeError("RPC error")

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        result = svc.transfer_fee(
            user_id=13,
            user_wallet=USER_WALLET,
            fee_amount_jpy=Decimal("1500"),
            subscription_amount_jpy=Decimal("0"),
            yield_excess_jpy=Decimal("0"),
            usd_jpy_rate=Decimal("150"),
        )

    assert result.status == "failed"
    assert result.tx_hash is None


# ---------------------------------------------------------------------------
# check_allowance
# ---------------------------------------------------------------------------


def test_check_allowance_returns_usd_amount():
    """allowance 5_000_000 raw (6 decimals) = 5 USD。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = _make_w3_mock(allowance=5_000_000, decimals=6)

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        allowance_usd = svc.check_allowance(USER_WALLET)

    assert allowance_usd == Decimal("5")


def test_check_allowance_disabled_config_returns_zero():
    """OPERATOR_FEE_WALLET_ADDRESS 未設定 → 0。"""
    svc = FeeTransferService(DISABLED_CFG)
    allowance_usd = svc.check_allowance(USER_WALLET)
    assert allowance_usd == Decimal("0")


# ---------------------------------------------------------------------------
# fee_usd 計算ロジック
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fee_jpy,sub_jpy,excess_jpy,rate,expected_usd",
    [
        (Decimal("15000"), Decimal("3000"), Decimal("2000"), Decimal("150"), Decimal("133.333333")),
        (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("150"), None),  # low_fee
        (Decimal("300"), Decimal("0"), Decimal("0"), Decimal("150"), Decimal("2.000000")),
    ],
)
def test_fee_usd_calculation(fee_jpy, sub_jpy, excess_jpy, rate, expected_usd):
    """fee_usd = (fee + sub + excess) / rate の変換確認。"""
    svc = FeeTransferService(BASE_SEPOLIA_CFG)
    mock_w3 = _make_w3_mock(allowance=1_000_000_000)

    with patch.object(svc, "_get_w3", return_value=mock_w3):
        result = svc.transfer_fee(
            user_id=20,
            user_wallet=USER_WALLET,
            fee_amount_jpy=fee_jpy,
            subscription_amount_jpy=sub_jpy,
            yield_excess_jpy=excess_jpy,
            usd_jpy_rate=rate,
        )

    if expected_usd is None:
        assert result.status == "low_fee"
    else:
        assert result.status == "sent"
        assert result.fee_usd == expected_usd
