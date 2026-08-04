# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_safe_yield_on_hold.py
"""[B1] HOLD 時の安全利回り提案 (_create_safe_yield_proposals_for_users) の単体テスト。

HOLD 判定でも遊休USDC→Aave USDC 供給を提案し(方向性ゲート非依存)、SUPPLY/USDC/aave 固定で
作られること、dedup/入金ゲート/fee ゲートで skip されること、フラグ既定 off を検証する。
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-safe-yield")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.automation.ai_judgment_scheduler as sched  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _create_safe_yield_proposals_for_users,
    _safe_yield_on_hold_enabled,
)
from app.proposals.models import Proposal  # noqa: E402


def _mk_user(uid: int = 11) -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.tier = "LOWER"
    return u


def _mk_db(users: list, pending: int = 0) -> MagicMock:
    db = MagicMock()
    active_res = MagicMock()
    active_res.all.return_value = users
    stale_res = MagicMock()
    stale_res.all.return_value = []
    # scalars: 1回目=active users、以降 各userにつき2回
    # (1: 可観測性チェックの直近3件クエリ / 2: stale expire クエリ)=空
    db.scalars.side_effect = [active_res] + [stale_res for _ in range(len(users) * 2)]
    db.scalar.return_value = pending  # dedup count
    return db


def _added_proposals(db: MagicMock) -> list:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Proposal)]


def _patch(monkeypatch: pytest.MonkeyPatch, *, amount: Decimal, should_trade: bool = True) -> None:
    monkeypatch.setattr(sched, "_is_user_due_for_judgment", lambda u, now: True)
    monkeypatch.setattr(sched, "_resolve_proposal_amount", lambda db, uid: amount)
    monkeypatch.setattr(
        sched, "normalize_tier", lambda tier, user_id=None: MagicMock(value="LOWER")
    )
    monkeypatch.setattr(sched, "estimate_static_gas_cost_usd", lambda op: Decimal("2"))
    fee = MagicMock()
    fee.should_trade = should_trade
    fee.fee_rate = Decimal("0")
    fee.fee_amount = Decimal("0")
    fee.reason = "ok"
    monkeypatch.setattr("app.fees.trade_gate.calculate_fee_by_market", lambda **kw: fee)
    monkeypatch.setattr("app.notifications.factory.get_notification_service", lambda: MagicMock())


def _decision() -> MagicMock:
    d = MagicMock()
    d.id = 1
    return d


def _result() -> MagicMock:
    r = MagicMock()
    r.final_confidence = 50
    return r


def test_flag_default_off() -> None:
    assert _safe_yield_on_hold_enabled() is False


def test_flag_on_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SAFE_YIELD_ON_HOLD_ENABLED", "true")
    assert _safe_yield_on_hold_enabled() is True


def test_creates_safe_supply_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    """funded user + no pending → SUPPLY/USDC/aave の提案が1件。"""
    _patch(monkeypatch, amount=Decimal("100"))
    db = _mk_db([_mk_user()], pending=0)
    n = _create_safe_yield_proposals_for_users(db, _decision(), _result())
    assert n == 1
    props = _added_proposals(db)
    assert len(props) == 1
    p = props[0]
    assert (p.operation, p.asset, p.protocol) == ("SUPPLY", "USDC", "aave")
    assert p.amount_usd == Decimal("100")
    assert "利回り" in p.reason
    # 消費者向け提案理由にプロトコル名（Aave 等）を出さない約束の回帰ガード。
    assert "Aave" not in p.reason and "aave" not in p.reason


def test_skip_when_pending_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """pending が1つでもあれば作らない (dedup)。"""
    _patch(monkeypatch, amount=Decimal("100"))
    db = _mk_db([_mk_user()], pending=1)
    assert _create_safe_yield_proposals_for_users(db, _decision(), _result()) == 0
    assert _added_proposals(db) == []


def test_skip_when_amount_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """入金未満/遊休なし (amount<=0) は skip。"""
    _patch(monkeypatch, amount=Decimal("0"))
    db = _mk_db([_mk_user()], pending=0)
    assert _create_safe_yield_proposals_for_users(db, _decision(), _result()) == 0
    assert _added_proposals(db) == []


def test_skip_when_fee_gate_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """fee ゲート should_trade=False は skip (少額でガス倒れ防止)。"""
    _patch(monkeypatch, amount=Decimal("100"), should_trade=False)
    db = _mk_db([_mk_user()], pending=0)
    assert _create_safe_yield_proposals_for_users(db, _decision(), _result()) == 0
    assert _added_proposals(db) == []
