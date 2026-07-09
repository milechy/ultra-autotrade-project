# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_scw_routing.py
"""委譲(SCW)経路の routing 判定 + 執行ヘルパー（2-D-C.2）の単体テスト。

dormant ゲート（_should_use_scw_route）・wallet id 解決・_execute_supply_via_scw の
build→send 連結を mock で検証する。実 Privy への送信は別途（staging-v4 shadow）。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from app.proposals.router import (
    _execute_supply_via_scw,
    _resolve_privy_wallet_id,
    _should_use_scw_route,
)
from app.proposals.scw_executor import ScwExecutionResult


@pytest.fixture()
def enabled_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DELEGATION_PRIVY_POLICY_ENABLED", "true")
    monkeypatch.setenv("PRIVY_SERVER_SIGNER_ID", "kq_server_1")
    monkeypatch.setenv("PRIVY_APP_ID", "app123")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret123")
    yield


def _grant(**kw: object) -> SimpleNamespace:
    base = {"wallet_address": "0xSCW", "privy_signer_id": "s1", "privy_policy_id": "p1"}
    base.update(kw)
    return SimpleNamespace(**base)


def _supply_proposal() -> SimpleNamespace:
    return SimpleNamespace(
        id=7, asset="USDC", amount_usd=Decimal("5"), operation="SUPPLY", protocol=None
    )


# ---- _resolve_privy_wallet_id ----


def test_resolve_wallet_id_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIVY_DELEGATED_WALLET_ID", "wid_env")
    assert _resolve_privy_wallet_id(SimpleNamespace()) == "wid_env"


def test_resolve_wallet_id_prefers_user_attr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIVY_DELEGATED_WALLET_ID", "wid_env")
    user = SimpleNamespace(privy_wallet_id="wid_user")
    assert _resolve_privy_wallet_id(user) == "wid_user"


def test_resolve_wallet_id_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRIVY_DELEGATED_WALLET_ID", raising=False)
    assert _resolve_privy_wallet_id(None) == ""


# ---- _should_use_scw_route ----


def test_route_false_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DELEGATION_PRIVY_POLICY_ENABLED", raising=False)
    assert _should_use_scw_route(_supply_proposal(), _grant()) is False


def test_route_true_when_enabled_supply_with_ids(enabled_env: None) -> None:
    assert _should_use_scw_route(_supply_proposal(), _grant()) is True


def test_route_false_for_withdraw(enabled_env: None) -> None:
    p = SimpleNamespace(
        id=8, asset="USDC", amount_usd=Decimal("5"), operation="WITHDRAW", protocol=None
    )
    assert _should_use_scw_route(p, _grant()) is False


def test_route_false_when_no_grant(enabled_env: None) -> None:
    assert _should_use_scw_route(_supply_proposal(), None) is False


def test_route_false_when_grant_missing_ids(enabled_env: None) -> None:
    assert _should_use_scw_route(_supply_proposal(), _grant(privy_signer_id=None)) is False
    assert _should_use_scw_route(_supply_proposal(), _grant(privy_policy_id=None)) is False


# ---- Pendle [Phase D / D3] ----


def _pendle_proposal() -> SimpleNamespace:
    return SimpleNamespace(
        id=9, asset="PT-yoUSD", amount_usd=Decimal("50"), operation="BUY_PT", protocol="pendle"
    )


def test_route_true_pendle_buy_pt_with_grant(enabled_env: None) -> None:
    """Pendle BUY_PT + grant.allowed_protocols に pendle → True。"""
    assert _should_use_scw_route(_pendle_proposal(), _grant(allowed_protocols=["pendle"])) is True


def test_route_false_pendle_without_allowed_protocol(enabled_env: None) -> None:
    """grant が pendle を委譲していない → False（Aave のみ委譲では Pendle を broadcast しない）。"""
    assert _should_use_scw_route(_pendle_proposal(), _grant(allowed_protocols=["aave"])) is False
    assert _should_use_scw_route(_pendle_proposal(), _grant(allowed_protocols=None)) is False


def test_route_true_pendle_sell_pt_redeem(enabled_env: None) -> None:
    """[D4] Pendle SELL_PT(満期出口 redeem)も委譲対象。"""
    p = SimpleNamespace(
        id=11, asset="PT-yoUSD", amount_usd=Decimal("50"), operation="SELL_PT", protocol="pendle"
    )
    assert _should_use_scw_route(p, _grant(allowed_protocols=["pendle"])) is True


def test_route_false_pendle_wrong_operation(enabled_env: None) -> None:
    """Pendle は BUY_PT / SELL_PT のみ委譲対象（その他 operation は custodial）。"""
    p = SimpleNamespace(
        id=10, asset="PT-yoUSD", amount_usd=Decimal("50"), operation="MINT_PT", protocol="pendle"
    )
    assert _should_use_scw_route(p, _grant(allowed_protocols=["pendle"])) is False


# ---- _execute_supply_via_scw ----


def test_execute_supply_via_scw_builds_and_sends(
    enabled_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRIVY_DELEGATED_WALLET_ID", "wid_env")
    # aave client build_deposit_txs を mock
    fake_client = MagicMock()
    fake_client.build_deposit_txs.return_value = {
        "approve_tx": {"to": "0xtoken", "data": "0xapprove", "value": "0x0"},
        "supply_tx": {"to": "0xpool", "data": "0xsupply", "value": "0x0"},
    }
    fake_service_obj = MagicMock()
    fake_service_obj.get_service.return_value.client = fake_client
    monkeypatch.setattr("app.aave.service.MultiChainAaveService", lambda: fake_service_obj)

    captured: dict = {}

    def fake_exec(**kw: object) -> ScwExecutionResult:
        captured.update(kw)
        return ScwExecutionResult(tx_hash="0xfeed", status="submitted", raw={})

    monkeypatch.setattr("app.proposals.scw_executor.execute_calls_via_scw", fake_exec)

    proposal = _supply_proposal()
    user = SimpleNamespace(smart_wallet_address="0xSCW", privy_wallet_id=None)
    result = _execute_supply_via_scw(proposal, "base", _grant(), user, MagicMock())

    assert result.tx_hash == "0xfeed"
    # build_deposit_txs に SCW アドレス / asset / amount(USD=token) が渡る
    fake_client.build_deposit_txs.assert_called_once()
    args, kwargs = fake_client.build_deposit_txs.call_args
    assert args[0] == "USDC"
    assert kwargs["wallet_address"] == "0xSCW"
    # execute_calls_via_scw に env wallet id / chain / 2 calls(approve→supply) が渡る
    assert captured["privy_wallet_id"] == "wid_env"
    assert captured["chain_name"] == "base"
    assert [c["to"] for c in captured["calls"]] == ["0xtoken", "0xpool"]
    assert captured["idempotency_key"] == "proposal-7"


def test_execute_supply_via_scw_requires_scw_address(
    enabled_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant = _grant(wallet_address=None)
    user = SimpleNamespace(smart_wallet_address=None, privy_wallet_id=None)
    with pytest.raises(ValueError):
        _execute_supply_via_scw(_supply_proposal(), "base", grant, user, MagicMock())
