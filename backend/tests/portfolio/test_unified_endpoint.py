# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/portfolio/test_unified_endpoint.py
"""統合ポートフォリオ endpoint の per-user fetch 層テスト（Asana 1215698091414471）。

Aave / Wallet ソースの fail-open 組み立てと、aggregate_portfolio への連結を検証する
（消費者個人スコープ: cex=None）。実 RPC/web3 は mock。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.portfolio.router import (
    _build_aave_source,
    _build_wallet_source,
    get_unified_portfolio,
)


def _account_data(collateral: str, debt: str, hf: str) -> SimpleNamespace:
    return SimpleNamespace(
        total_collateral_usd=Decimal(collateral),
        total_debt_usd=Decimal(debt),
        health_factor=Decimal(hf),
    )


def _wallet_resp(total: str, fallback: bool = False) -> SimpleNamespace:
    return SimpleNamespace(total_usd=Decimal(total), fallback_used=fallback)


# ---- _build_aave_source ----


def test_aave_source_success() -> None:
    client = MagicMock()
    client.get_account_data.return_value = _account_data("1000", "300", "2.5")
    with patch("app.aave.client.get_default_aave_client", return_value=client):
        s = _build_aave_source("0xwallet")
    assert s is not None
    assert s.source == "aave"
    assert s.total_usd == Decimal("700")  # collateral - debt
    assert s.supply_usd == Decimal("1000")
    assert s.borrow_usd == Decimal("300")
    assert s.health_factor == Decimal("2.5")
    assert s.available is True


def test_aave_source_fail_open() -> None:
    with patch("app.aave.client.get_default_aave_client", side_effect=RuntimeError("rpc down")):
        assert _build_aave_source("0xwallet") is None


def test_aave_source_caps_infinite_hf() -> None:
    client = MagicMock()
    client.get_account_data.return_value = _account_data("1000", "0", "Infinity")
    with patch("app.aave.client.get_default_aave_client", return_value=client):
        s = _build_aave_source("0xwallet")
    assert s is not None
    assert s.health_factor == Decimal("999.0")  # _cap_hf_inf


# ---- _build_wallet_source ----


@pytest.mark.asyncio
async def test_wallet_source_success() -> None:
    with patch(
        "app.partner.wallet_balance_service.fetch",
        new=AsyncMock(return_value=_wallet_resp("250")),
    ):
        s = await _build_wallet_source("0xwallet")
    assert s is not None
    assert s.source == "wallet"
    assert s.total_usd == Decimal("250")
    assert s.available is True


@pytest.mark.asyncio
async def test_wallet_source_fallback_marks_unavailable() -> None:
    with patch(
        "app.partner.wallet_balance_service.fetch",
        new=AsyncMock(return_value=_wallet_resp("0", fallback=True)),
    ):
        s = await _build_wallet_source("0xwallet")
    assert s is not None
    assert s.available is False  # RPC フォールバックは grand_total から除外


@pytest.mark.asyncio
async def test_wallet_source_fail_open() -> None:
    with patch(
        "app.partner.wallet_balance_service.fetch",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        assert await _build_wallet_source("0xwallet") is None


# ---- get_unified_portfolio (assembly) ----


@pytest.mark.asyncio
async def test_unified_aggregates_aave_and_wallet() -> None:
    client = MagicMock()
    client.get_account_data.return_value = _account_data("1000", "300", "2.5")
    user = SimpleNamespace(smart_wallet_address="0xSCW", wallet_address=None)
    with (
        patch("app.aave.client.get_default_aave_client", return_value=client),
        patch(
            "app.partner.wallet_balance_service.fetch",
            new=AsyncMock(return_value=_wallet_resp("250")),
        ),
    ):
        view = await get_unified_portfolio(current_user=user)  # type: ignore[arg-type]
    assert view.aave_net_usd == Decimal("700")
    assert view.wallet_usd == Decimal("250")
    assert view.cex_usd == Decimal("0")  # 消費者スコープ: CEX なし
    assert view.grand_total_usd == Decimal("950")
    assert view.health_factor == Decimal("2.5")
    assert view.sources_available == 2
    assert view.degraded is True  # cex 欠落のため 2/3


@pytest.mark.asyncio
async def test_unified_no_wallet_is_empty_degraded() -> None:
    user = SimpleNamespace(smart_wallet_address=None, wallet_address=None)
    view = await get_unified_portfolio(current_user=user)  # type: ignore[arg-type]
    assert view.grand_total_usd == Decimal("0")
    assert view.sources_available == 0
    assert view.degraded is True


@pytest.mark.asyncio
async def test_unified_aave_fail_open_wallet_only() -> None:
    user = SimpleNamespace(smart_wallet_address="0xSCW", wallet_address=None)
    with (
        patch("app.aave.client.get_default_aave_client", side_effect=RuntimeError("down")),
        patch(
            "app.partner.wallet_balance_service.fetch",
            new=AsyncMock(return_value=_wallet_resp("250")),
        ),
    ):
        view = await get_unified_portfolio(current_user=user)  # type: ignore[arg-type]
    assert view.aave_net_usd == Decimal("0")
    assert view.wallet_usd == Decimal("250")
    assert view.grand_total_usd == Decimal("250")
    assert view.sources_available == 1
