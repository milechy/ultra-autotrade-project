# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_credit_delegation_tx.py
"""Web3AaveClient.build_approve_delegation_tx のユニットテスト（Credit Delegation 第2スライス）。

第1スライス（assess_delegated_borrow）の安全枠（approved_usd）を上限に、Aave V3 variable debt
token の approveDelegation 未署名 tx を構築する経路をカバーする。

検証ポイント:
- dry_run=True / dry_run=False いずれでも send_raw_transaction を一切呼ばない（broadcast 非実装）
- 安全枠超（approved_usd<=0）は AaveClientError で拒否
- requested>approved のとき amount_wei が approved ベースにクランプされる
- Decimal→wei が途中 float 化なしで正確（USDC 6 decimals）
- 空 delegatee / 空 wallet_address で fail-fast
- encode_abi("approveDelegation", args=[...]) が呼ばれる
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

pytest.importorskip("web3")

from app.aave.client import AaveClientError, Web3AaveClient
from app.aave.credit_delegation import DelegationAssessment, assess_delegated_borrow

# テスト用アドレス（checksum 化可能な値）
_WALLET = "0x52908400098527886E0F7030069857D2E4169EE7"
_DELEGATEE = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
_USDC_UNDERLYING = "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8"
_VDEBT_TOKEN = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
_CHAIN_ID = 84532  # Base Sepolia
_USDC_DECIMALS = 6


def _make_assessment(
    *,
    requested: str,
    approved: str,
) -> DelegationAssessment:
    """approved_usd を任意指定した DelegationAssessment を組み立てる。"""
    return DelegationAssessment(
        requested_usd=Decimal(requested),
        approved_usd=Decimal(approved),
        max_borrow_usd=Decimal(approved),
        projected_hf=Decimal("1.8"),
        within_floor=True,
        reason="test fixture",
    )


def _make_client(*, encoded_data: str = "0xdeadbeef") -> Web3AaveClient:
    """__init__ を回避して _pool / _w3 / token_addresses を mock 注入した client。"""
    client = object.__new__(Web3AaveClient)

    # variable debt token contract (decimals / encode_abi / functions.* を持つ)
    debt_contract = MagicMock()
    debt_contract.functions.decimals.return_value.call.return_value = _USDC_DECIMALS
    debt_contract.encode_abi.return_value = encoded_data

    # _w3.eth.contract(...) は debt token contract を返す
    w3 = MagicMock()
    w3.eth.chain_id = _CHAIN_ID
    w3.eth.contract.return_value = debt_contract

    # _pool.functions.getReserveData(asset).call()[10] = variableDebtTokenAddress
    reserve_data = [None] * 15
    reserve_data[10] = _VDEBT_TOKEN
    pool = MagicMock()
    pool.functions.getReserveData.return_value.call.return_value = reserve_data

    client._w3 = w3  # type: ignore[attr-defined]
    client._pool = pool  # type: ignore[attr-defined]
    client.token_addresses = {"USDC": _USDC_UNDERLYING}  # type: ignore[attr-defined]
    # broadcast 経路の不在を検証するための spy
    w3.eth.send_raw_transaction = MagicMock()

    return client


# ─────────────────────────────────────────────────────────────────────────────
# dry_run=True
# ─────────────────────────────────────────────────────────────────────────────


def test_dry_run_returns_summary_without_tx() -> None:
    """dry_run=True は試算 dict のみ返し、tx 構築・broadcast をしない。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="100")

    result = client.build_approve_delegation_tx(
        asset_symbol="USDC",
        delegatee=_DELEGATEE,
        delegation_assessment=assessment,
        wallet_address=_WALLET,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["approved_usd"] == "100"
    assert result["asset_symbol"] == "USDC"
    # getReserveData / decimals / encode_abi / send_raw_transaction いずれも未呼出
    client._pool.functions.getReserveData.assert_not_called()  # type: ignore[attr-defined]
    client._w3.eth.contract.assert_not_called()  # type: ignore[attr-defined]
    client._w3.eth.send_raw_transaction.assert_not_called()  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# dry_run=False
# ─────────────────────────────────────────────────────────────────────────────


def test_real_run_builds_unsigned_tx_without_broadcast() -> None:
    """dry_run=False は未署名 tx dict を返し、send_raw_transaction を呼ばない。"""
    client = _make_client(encoded_data="0xabc123")
    assessment = _make_assessment(requested="100", approved="100")

    result = client.build_approve_delegation_tx(
        asset_symbol="USDC",
        delegatee=_DELEGATEE,
        delegation_assessment=assessment,
        wallet_address=_WALLET,
        dry_run=False,
    )

    tx = result["approve_delegation_tx"]
    from web3 import Web3

    assert tx["to"] == Web3.to_checksum_address(_VDEBT_TOKEN)
    assert tx["data"] == "0xabc123"
    assert tx["from"] == Web3.to_checksum_address(_WALLET)
    assert tx["chainId"] == _CHAIN_ID
    assert tx["value"] == "0x0"
    # broadcast 非実装の保証
    client._w3.eth.send_raw_transaction.assert_not_called()  # type: ignore[attr-defined]


def test_real_run_calls_encode_abi_approve_delegation() -> None:
    """approveDelegation の encode_abi が checksum delegatee + wei amount で呼ばれる。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="100")

    client.build_approve_delegation_tx(
        asset_symbol="USDC",
        delegatee=_DELEGATEE,
        delegation_assessment=assessment,
        wallet_address=_WALLET,
        dry_run=False,
    )

    from web3 import Web3

    debt_contract = client._w3.eth.contract.return_value  # type: ignore[attr-defined]
    debt_contract.encode_abi.assert_called_once()
    call = debt_contract.encode_abi.call_args
    assert call.args[0] == "approveDelegation"
    args = call.kwargs["args"]
    assert args[0] == Web3.to_checksum_address(_DELEGATEE)
    # 100 USDC × 10^6
    assert args[1] == 100_000_000


# ─────────────────────────────────────────────────────────────────────────────
# 安全枠超拒否
# ─────────────────────────────────────────────────────────────────────────────


def test_zero_approved_rejected() -> None:
    """approved_usd=0（安全枠超 / headroom なし）は AaveClientError で拒否。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="0")

    with pytest.raises(AaveClientError):
        client.build_approve_delegation_tx(
            asset_symbol="USDC",
            delegatee=_DELEGATEE,
            delegation_assessment=assessment,
            wallet_address=_WALLET,
            dry_run=False,
        )

    # 拒否時は tx 構築も broadcast もしない
    client._pool.functions.getReserveData.assert_not_called()  # type: ignore[attr-defined]
    client._w3.eth.send_raw_transaction.assert_not_called()  # type: ignore[attr-defined]


def test_negative_approved_rejected() -> None:
    """approved_usd<0 も AaveClientError で拒否。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="-5")

    with pytest.raises(AaveClientError):
        client.build_approve_delegation_tx(
            asset_symbol="USDC",
            delegatee=_DELEGATEE,
            delegation_assessment=assessment,
            wallet_address=_WALLET,
            dry_run=False,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 安全枠クランプ連携（第1スライスの assess_delegated_borrow と統合）
# ─────────────────────────────────────────────────────────────────────────────


def test_amount_wei_uses_approved_when_requested_exceeds() -> None:
    """requested>approved のとき amount_wei は approved ベース（クランプ反映）。"""
    # 安全枠を実際の assess_delegated_borrow で算出: collateral 1000, lt 0.8, floor 1.6
    # max_borrow = 1000*0.8/1.6 - 0 = 500。requested=900 → approved=500 にクランプ。
    assessment = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        requested_borrow_usd=Decimal("900"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert assessment.requested_usd == Decimal("900")
    assert assessment.approved_usd == Decimal("500")

    client = _make_client()
    client.build_approve_delegation_tx(
        asset_symbol="USDC",
        delegatee=_DELEGATEE,
        delegation_assessment=assessment,
        wallet_address=_WALLET,
        dry_run=False,
    )

    debt_contract = client._w3.eth.contract.return_value  # type: ignore[attr-defined]
    args = debt_contract.encode_abi.call_args.kwargs["args"]
    # 500 USDC × 10^6（requested 900 ではない）
    assert args[1] == 500_000_000


def test_decimal_to_wei_no_float_drift() -> None:
    """Decimal("100.123456") × 10^6 が float 誤差なく整数化される。"""
    client = _make_client()
    assessment = _make_assessment(requested="100.123456", approved="100.123456")

    client.build_approve_delegation_tx(
        asset_symbol="USDC",
        delegatee=_DELEGATEE,
        delegation_assessment=assessment,
        wallet_address=_WALLET,
        dry_run=False,
    )

    debt_contract = client._w3.eth.contract.return_value  # type: ignore[attr-defined]
    args = debt_contract.encode_abi.call_args.kwargs["args"]
    assert args[1] == 100_123_456
    assert isinstance(args[1], int)


# ─────────────────────────────────────────────────────────────────────────────
# fail-fast（空アドレス）
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_delegatee_fails_fast() -> None:
    """空 delegatee は AaveClientError で即時失敗。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="100")

    with pytest.raises(AaveClientError):
        client.build_approve_delegation_tx(
            asset_symbol="USDC",
            delegatee="",
            delegation_assessment=assessment,
            wallet_address=_WALLET,
            dry_run=False,
        )
    client._w3.eth.send_raw_transaction.assert_not_called()  # type: ignore[attr-defined]


def test_empty_wallet_fails_fast() -> None:
    """空 wallet_address は AaveClientError で即時失敗。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="100")

    with pytest.raises(AaveClientError):
        client.build_approve_delegation_tx(
            asset_symbol="USDC",
            delegatee=_DELEGATEE,
            delegation_assessment=assessment,
            wallet_address="",
            dry_run=False,
        )
    client._w3.eth.send_raw_transaction.assert_not_called()  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# 資産未解決
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_asset_rejected() -> None:
    """token_addresses に無いシンボルは AaveClientError。"""
    client = _make_client()
    assessment = _make_assessment(requested="100", approved="100")

    with pytest.raises(AaveClientError):
        client.build_approve_delegation_tx(
            asset_symbol="DAI",
            delegatee=_DELEGATEE,
            delegation_assessment=assessment,
            wallet_address=_WALLET,
            dry_run=False,
        )
