# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_redeem.py
"""[Phase D / D4] Pendle SELL_PT(満期出口 redeem) PT→USDC 経路。

_build_pendle_swap_result が operation で buy/sell を振り分けること、SELL_PT の dry-run が
build_sell_pt_swap_result を PT(18桁)→USDC(6桁) の正しい引数で呼ぶことを検証する
（broadcast しない・全て monkeypatch）。
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-pendle-redeem")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.protocols.pendle.client as pendle_client_mod  # noqa: E402
import app.protocols.pendle.config as pendle_config_mod  # noqa: E402
from app.proposals.router import (  # noqa: E402
    PendleDryRunNotBroadcast,
    _build_pendle_swap_result,
    _execute_pendle_for_proposal,
)
from app.protocols.pendle.config import PendleConfig  # noqa: E402
from app.protocols.pendle.schemas import RouterV4SwapResult  # noqa: E402

_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
_MARKET = "0x1111111111111111111111111111111111111111"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_WALLET = "0x7f9300000000000000000000000000000000a0Ff"


class _FakeClient:
    def __init__(self) -> None:
        self.buy_calls: list[dict[str, object]] = []
        self.sell_calls: list[dict[str, object]] = []

    async def build_buy_pt_swap_result(self, **kwargs: object) -> RouterV4SwapResult:
        self.buy_calls.append(kwargs)
        return RouterV4SwapResult(success=True, to=_ROUTER, calldata="0x" + "aa" * 50, approvals=[])

    async def build_sell_pt_swap_result(self, **kwargs: object) -> RouterV4SwapResult:
        self.sell_calls.append(kwargs)
        return RouterV4SwapResult(success=True, to=_ROUTER, calldata="0x" + "bb" * 50, approvals=[])


def _config() -> PendleConfig:
    return PendleConfig(
        market_address=_MARKET,
        underlying_token_address=_USDC,
        underlying_token_decimals=6,
        stable_underlying=True,
        chain="base_sepolia",
    )


def _mk_proposal(operation: str) -> MagicMock:
    p = MagicMock()
    p.id = 88
    p.protocol = "pendle"
    p.operation = operation
    p.amount_usd = Decimal("50.00")
    p.user_id = 11
    return p


def test_build_result_routes_sell_pt(monkeypatch: pytest.MonkeyPatch) -> None:
    """SELL_PT → build_sell_pt_swap_result(token_out=USDC・6桁・pt_amount=amount_usd)。"""
    client = _FakeClient()
    monkeypatch.setattr(pendle_client_mod, "get_pendle_router_v4_client", lambda cfg: client)
    result = _build_pendle_swap_result(_mk_proposal("SELL_PT"), _config(), _WALLET)
    assert result.success and result.calldata.startswith("0xbb")
    assert len(client.sell_calls) == 1 and not client.buy_calls
    call = client.sell_calls[0]
    assert call["token_out"] == _USDC
    assert call["pt_amount_in"] == Decimal("50.00")
    assert call["from_address"] == _WALLET
    assert call["token_out_decimals"] == 6


def test_build_result_routes_buy_pt(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUY_PT → build_buy_pt_swap_result（従来経路）。"""
    client = _FakeClient()
    monkeypatch.setattr(pendle_client_mod, "get_pendle_router_v4_client", lambda cfg: client)
    result = _build_pendle_swap_result(_mk_proposal("BUY_PT"), _config(), _WALLET)
    assert result.calldata.startswith("0xaa")
    assert len(client.buy_calls) == 1 and not client.sell_calls


def test_sell_pt_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """SELL_PT の dry-run: calldata 構築のみ → PendleDryRunNotBroadcast（broadcast なし）。"""
    client = _FakeClient()
    monkeypatch.setattr(pendle_config_mod, "get_pendle_config", lambda: _config())
    monkeypatch.setattr(pendle_client_mod, "get_pendle_router_v4_client", lambda cfg: client)

    db = MagicMock()
    user = MagicMock()
    user.wallet_address = _WALLET
    user.smart_wallet_address = None
    db.get.return_value = user

    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal("SELL_PT"), db)
    assert len(client.sell_calls) == 1  # 出口 calldata を構築した
