# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_liquidity_guard.py
"""[Phase D / D5] 流動性ガード (_pendle_liquidity_blocked)。

1 投入がプール流動性(tvl_usd)の数% + 絶対上限を超えないことを検査し、tvl 未知(API失敗/0)は
fail-closed で block することを検証する。
"""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-pendle-liq")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.protocols.pendle.client as pendle_client_mod  # noqa: E402
from app.proposals.router import _pendle_liquidity_blocked  # noqa: E402
from app.protocols.pendle.config import PendleConfig  # noqa: E402

_MARKET = "0x1111111111111111111111111111111111111111"


def _config() -> PendleConfig:
    return PendleConfig(
        market_address=_MARKET,
        max_pool_liquidity_pct=Decimal("0.05"),
        max_trade_usd_cap=Decimal("5000"),
    )


def _patch_market(monkeypatch: pytest.MonkeyPatch, *, tvl: object, raises: bool = False) -> None:
    class _Client:
        async def get_market_info(self, market_address: str) -> object:
            if raises:
                raise RuntimeError("pendle API down")
            return SimpleNamespace(tvl_usd=tvl)

    monkeypatch.setattr(pendle_client_mod, "get_pendle_client", lambda cfg: _Client())


def test_pass_when_within_pool_and_abs_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """tvl 十分・amount ≤ 5% かつ ≤ 絶対上限 → None(通過)。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"))
    assert _pendle_liquidity_blocked(_config(), Decimal("1000")) is None


def test_block_when_exceeds_pool_pct(monkeypatch: pytest.MonkeyPatch) -> None:
    """amount > tvl×5%(=5700) → block。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"))
    reason = _pendle_liquidity_blocked(_config(), Decimal("6000"))
    assert reason is not None and "プール流動性上限" in reason


def test_block_when_exceeds_abs_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """pool% は満たすが絶対上限 5000 を超える → block。"""
    _patch_market(monkeypatch, tvl=Decimal("1000000"))  # 5% = 50000 で余裕
    reason = _pendle_liquidity_blocked(_config(), Decimal("6000"))
    assert reason is not None and "絶対上限" in reason


def test_block_when_tvl_zero_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """tvl=0(API失敗の fail-open 値) → fail-closed で block。"""
    _patch_market(monkeypatch, tvl=Decimal("0"))
    reason = _pendle_liquidity_blocked(_config(), Decimal("1"))
    assert reason is not None and "fail-closed" in reason


def test_block_when_market_info_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_market_info 例外 → fail-closed で block(壊さない保証ができない)。"""
    _patch_market(monkeypatch, tvl=Decimal("0"), raises=True)
    reason = _pendle_liquidity_blocked(_config(), Decimal("1000"))
    assert reason is not None and "fail-closed" in reason
