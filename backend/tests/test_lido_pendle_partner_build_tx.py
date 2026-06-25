# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_lido_pendle_partner_build_tx.py
"""Lido/Pendle 非カストディアル build_*_tx のテスト。

[非カストディアル化] LidoClient.build_stake_tx / PendleRouterV4Client.build_buy_pt_tx は
サーバー秘密鍵 (wallet_private_key) を一切参照せず、未署名 tx dict を返して partner が
Privy 本人署名する。本テストは以下を保証する:

- DummyLidoClient.build_stake_tx が partner 本人を from に、添付 ETH を value に持つ dict を返す
- LidoClient.build_stake_tx (web3 実 encode) が submit calldata を組み、秘密鍵不要で動く
- build_stake_tx が wallet_private_key を参照しない (空鍵 config でも成功)
- PendleRouterV4Client.build_buy_pt_tx が SDK calldata を未署名 tx に変換する
- Router 不一致 / calldata 欠損は PendleBuildTxError で fail-closed (未署名 tx を返さない)
- PartnerUnsignedTxs に STAKE_ETH / BUY_PT 用フィールドが存在する
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import pytest

from app.proposals.schemas import PartnerUnsignedTxs
from app.protocols.lido.client import DummyLidoClient, LidoClient
from app.protocols.lido.config import LidoConfig
from app.protocols.pendle.client import (
    PendleBuildTxError,
    PendleRouterV4Client,
)
from app.protocols.pendle.config import PendleConfig

_PARTNER = "0x000000000000000000000000000000000000abcd"
_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"


# ---------------------------------------------------------------------------
# Lido: DummyLidoClient.build_stake_tx (DoD #2)
# ---------------------------------------------------------------------------
def test_dummy_lido_build_stake_tx_shape() -> None:
    """Dummy が from=partner / value=添付 ETH を持つ未署名 tx dict を返す。"""
    client = DummyLidoClient(LidoConfig())
    amount_wei = 1_000_000_000_000_000_000  # 1 ETH
    tx = client.build_stake_tx(amount_wei=amount_wei, from_address=_PARTNER)
    assert tx["from"] == _PARTNER
    assert tx["value"] == hex(amount_wei)
    assert tx["to"] == client._config.steth_contract_address
    assert set(tx.keys()) == {"to", "data", "from", "chainId", "value"}


def test_lido_resolve_chain_id_fail_closed_on_unknown() -> None:
    """未知 chain 名は mainnet へ fallback せず fail-closed (誤ネットワーク署名防止)。"""
    from app.protocols.lido.client import _resolve_chain_id  # noqa: PLC0415

    assert _resolve_chain_id("holesky") == 17000
    assert _resolve_chain_id("mainnet") == 1
    with pytest.raises(ValueError):
        _resolve_chain_id("base-sepolia")  # マップ外 → 1 に黙って落とさない
    with pytest.raises(ValueError):
        _resolve_chain_id("")


def test_dummy_lido_build_stake_tx_rejects_bad_args() -> None:
    """from 未指定 / 非正数 amount は ValueError。"""
    client = DummyLidoClient(LidoConfig())
    with pytest.raises(ValueError):
        client.build_stake_tx(amount_wei=1, from_address="")
    with pytest.raises(ValueError):
        client.build_stake_tx(amount_wei=0, from_address=_PARTNER)


def test_lido_build_stake_tx_does_not_use_private_key() -> None:
    """build_stake_tx は wallet_private_key を参照しない (空鍵 config でも成功)。"""
    pytest.importorskip("web3")
    # 秘密鍵を空にした config。custodial stake_eth は失敗するが build_stake_tx は成功する。
    config = LidoConfig(wallet_private_key="")
    client = LidoClient(config)
    amount_wei = 500_000_000_000_000_000  # 0.5 ETH
    tx = client.build_stake_tx(amount_wei=amount_wei, from_address=_PARTNER)
    # submit calldata の先頭 4byte は submit(address) のセレクタ。空でないことを確認。
    assert tx["data"].startswith("0x")
    assert len(tx["data"]) > 2
    assert tx["value"] == hex(amount_wei)
    # from は checksum 化された partner。サーバー鍵由来のアドレスではない。
    assert tx["from"].lower() == _PARTNER.lower()


# ---------------------------------------------------------------------------
# Pendle: PendleRouterV4Client.build_buy_pt_tx
# ---------------------------------------------------------------------------
def _sdk_response(to_addr: str, calldata: str = "0xdeadbeef") -> dict[str, Any]:
    return {
        "data": {
            "tx": {"to": to_addr, "data": calldata},
            "amountOut": "990000000000000000",
            "approvals": [],
        }
    }


@pytest.mark.asyncio
async def test_pendle_build_buy_pt_tx_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK calldata を未署名 tx に変換し、from/receiver=partner を固定する。"""
    config = PendleConfig(router_address=_ROUTER)
    client = PendleRouterV4Client(config)

    captured: dict[str, Any] = {}

    async def _fake_call_sdk(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        captured["endpoint"] = endpoint
        captured["params"] = params
        return _sdk_response(_ROUTER, "0xabc123")

    monkeypatch.setattr(client, "_call_sdk", _fake_call_sdk)

    tx = await client.build_buy_pt_tx(
        market_address="0x" + "11" * 20,
        token_in="0x" + "22" * 20,
        amount_in=Decimal("1.0"),
        from_address=_PARTNER,
    )
    assert tx["to"].lower() == _ROUTER.lower()
    assert tx["data"] == "0xabc123"
    assert tx["from"] == _PARTNER
    assert tx["value"] == "0x0"
    # receiver は partner 本人 (PT が本人着金)。
    assert captured["params"]["receiver"] == _PARTNER
    assert captured["endpoint"] == "swapExactTokenForPt"


@pytest.mark.asyncio
async def test_pendle_build_buy_pt_tx_router_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK calldata の宛先が Router でない場合は未署名 tx を返さず PendleBuildTxError。"""
    config = PendleConfig(router_address=_ROUTER)
    client = PendleRouterV4Client(config)

    async def _evil_call_sdk(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        return _sdk_response("0x" + "ee" * 20, "0xevil")  # 攻撃者コントラクト宛

    monkeypatch.setattr(client, "_call_sdk", _evil_call_sdk)

    with pytest.raises(PendleBuildTxError):
        await client.build_buy_pt_tx(
            market_address="0x" + "11" * 20,
            token_in="0x" + "22" * 20,
            amount_in=Decimal("1.0"),
            from_address=_PARTNER,
        )


@pytest.mark.asyncio
async def test_pendle_build_buy_pt_tx_rejects_bad_args() -> None:
    """from 未指定 / 非正数 amount は PendleBuildTxError。"""
    client = PendleRouterV4Client(PendleConfig(router_address=_ROUTER))
    with pytest.raises(PendleBuildTxError):
        await client.build_buy_pt_tx(
            market_address="0x" + "11" * 20,
            token_in="0x" + "22" * 20,
            amount_in=Decimal("1.0"),
            from_address="",
        )
    with pytest.raises(PendleBuildTxError):
        await client.build_buy_pt_tx(
            market_address="0x" + "11" * 20,
            token_in="0x" + "22" * 20,
            amount_in=Decimal("0"),
            from_address=_PARTNER,
        )


# ---------------------------------------------------------------------------
# schema: PartnerUnsignedTxs に STAKE_ETH / BUY_PT フィールド (DoD #4)
# ---------------------------------------------------------------------------
def test_partner_unsigned_txs_has_stake_and_buy_pt_fields() -> None:
    """PartnerUnsignedTxs が stake_tx (STAKE_ETH) / buy_pt_tx (BUY_PT) を持つ。"""
    fields = PartnerUnsignedTxs.model_fields
    assert "stake_tx" in fields
    assert "buy_pt_tx" in fields
    # 既存 Aave フィールドも維持 (後方互換)。
    assert "approve_tx" in fields
    assert "supply_tx" in fields
    assert "withdraw_tx" in fields


# ---------------------------------------------------------------------------
# endpoint helper: USD→token 換算未配線につき fail-closed (501)
# ---------------------------------------------------------------------------
def _mk_proposal(operation: str, amount_usd: str = "100") -> Any:
    from unittest.mock import MagicMock  # noqa: PLC0415

    p = MagicMock()
    p.id = 1
    p.operation = operation
    p.amount = Decimal(amount_usd)
    p.amount_usd = Decimal(amount_usd)
    return p


def test_lido_build_partner_tx_fail_closed_501() -> None:
    """Lido build-tx は USD→ETH 換算未配線のため 501 で fail-closed (誤数量を組まない)。"""
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-build-tx")
    os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
    from fastapi import HTTPException  # noqa: PLC0415

    from app.proposals.router import _build_lido_partner_tx  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc_info:
        _build_lido_partner_tx(_mk_proposal("STAKE_ETH"), "0x" + "ab" * 20)
    assert exc_info.value.status_code == 501


def test_pendle_build_partner_tx_fail_closed_501() -> None:
    """Pendle build-tx は USD→token 換算未配線のため 501 で fail-closed。"""
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-build-tx")
    os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
    from fastapi import HTTPException  # noqa: PLC0415

    from app.proposals.router import _build_pendle_partner_tx  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc_info:
        _build_pendle_partner_tx(_mk_proposal("BUY_PT"), "0x" + "ab" * 20)
    assert exc_info.value.status_code == 501


def test_build_partner_tx_wrong_operation_422() -> None:
    """protocol と operation の不一致は 422 (501 ガードより先に弾く)。"""
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-build-tx")
    os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
    from fastapi import HTTPException  # noqa: PLC0415

    from app.proposals.router import _build_lido_partner_tx  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc_info:
        _build_lido_partner_tx(_mk_proposal("SUPPLY"), "0x" + "ab" * 20)
    assert exc_info.value.status_code == 422
