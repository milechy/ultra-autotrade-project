# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_real_funds_execution_gates.py
"""実資金投入前に閉じた 2 つのゲートの回帰テスト（2026-08-06）。

背景: 「完全おまかせ」を実資金で動かすために `AUTO_EXECUTION_ENABLED=true` にする、
という操作の副作用として以下 2 つが起きることが本番調査で判明した。

1. `AUTO_EXECUTION_ENABLED` は執行段階のマスタースイッチで、委譲(SCW)経路は
   `_execute_aave_for_proposal` の内側にある。つまり true にすると、**委譲枠を持たない
   ユーザーの承認までサーバー単一鍵(`AAVE_WALLET_PRIVATE_KEY`)でプール資金を動かす経路**が
   同時に開く。→ `CUSTODIAL_EXECUTION_ENABLED`（既定 false）に分離した。

2. 入金ゲート / 提案サイジングが `fund_allocations`（custodial プール持分の**帳簿行**）を
   最優先していた。SCW を持つユーザーの執行は本人 SCW から行われるため、帳簿額でゲートを
   通すと「$200 ゲート通過 → SCW 残高 0 で on-chain revert」になる。本番 user 11 が
   allocation $4,600 / SCW 実残高 $0 でこの状態だった。→ SCW 保有ユーザーは実残高のみを
   資金源とみなす（`uses_custodial_allocation`）。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.aave.schemas import AaveOperationResult, AaveOperationStatus, AaveOperationType
from app.auth.models import User
from app.automation.safety_gate import HardStopResult
from app.database import Base
from app.partner.allocation_models import FundAllocation
from app.proposals.models import Proposal

_EOA = "0x999e696e4c595356b29dd5314fad29247022a3a8"
_SCW = "0x5d7769d41e4af7f1153b94909702e8db382f3158"


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _make_user(db: Session, uid: int, *, scw: str | None = None) -> User:
    user = User(
        id=uid,
        email=f"gate{uid}@test.com",
        username=f"gate{uid}",
        hashed_password="x",
        role="partner",
        is_active=True,
        wallet_address=_EOA,
        smart_wallet_address=scw,
    )
    db.add(user)
    db.flush()
    return user


def _make_allocation(db: Session, user_id: int, amount: str) -> FundAllocation:
    allocation = FundAllocation(
        partner_id=1,
        tester_name=f"tester{user_id}",
        tester_user_id=user_id,
        allocated_amount_usd=Decimal(amount),
        status="active",
    )
    db.add(allocation)
    db.flush()
    return allocation


def _make_proposal(db: Session, user_id: int) -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="real-funds gate test",
        status="approved",
        approved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    return proposal


def _fake_result() -> AaveOperationResult:
    return AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000.00"),
        tx_hash="0xdeadbeef",
    )


# --------------------------------------------------------------------------- #
# ゲート 1: custodial 単一鍵実行の分離
# --------------------------------------------------------------------------- #
def test_custodial_execution_disabled_by_default(db_session: Session) -> None:
    """★委譲枠なしユーザーは、既定でサーバー単一鍵実行に落ちないこと。

    ここが壊れると `AUTO_EXECUTION_ENABLED=true` にした瞬間に、委譲枠を持たない
    admin/partner/viewer の承認クリックがプール資金を実際に動かす。
    """
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session, uid=101)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    with (
        patch.dict(os.environ, {}, clear=False),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch("app.aave.risk_limiter.check_trade_within_limits", return_value=None),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=lambda **_: called.append(True) or _fake_result(),
        ),
    ):
        os.environ.pop("CUSTODIAL_EXECUTION_ENABLED", None)
        _execute_aave_for_proposal(proposal, db_session)

    assert called == [], "custodial 単一鍵実行が既定で走ってしまっている"
    # transient 扱い: 手動署名フローで拾えるよう 'approved' のまま据え置く。
    assert proposal.status == "approved"


def test_custodial_execution_runs_when_explicitly_enabled(db_session: Session) -> None:
    """明示的に CUSTODIAL_EXECUTION_ENABLED=true にしたときのみ従来経路が動く。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session, uid=102)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch("app.aave.risk_limiter.check_trade_within_limits", return_value=None),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=lambda **_: called.append(True) or _fake_result(),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == [True]
    assert proposal.status == "executed"


# --------------------------------------------------------------------------- #
# ゲート 2: SCW ユーザーは帳簿でなく実残高を資金源にする
# --------------------------------------------------------------------------- #
def test_scw_user_deposit_ignores_custodial_allocation(db_session: Session) -> None:
    """★本番 user 11 の形: allocation $4,600 / SCW 実残高 $0 → 判定は実残高側。

    ここが壊れると帳簿額で $200 ゲートを通過し、残高 0 の SCW に supply して revert する。
    """
    from app.users.deposit_resolver import resolve_user_deposit_usd

    user = _make_user(db_session, uid=103, scw=_SCW)
    _make_allocation(db_session, user.id, "4600")
    db_session.commit()

    with patch("app.aave.balance.read_wallet_usdc_balance", return_value=Decimal("0")) as m:
        deposit = resolve_user_deposit_usd(db_session, user.id)

    assert deposit == Decimal("0"), "帳簿額 $4,600 が使われている"
    m.assert_called_once_with(_SCW)


def test_custodial_user_still_uses_allocation(db_session: Session) -> None:
    """SCW を持たない custodial パートナー/テスターは従来どおり allocation を使う（非回帰）。"""
    from app.users.deposit_resolver import resolve_user_deposit_usd

    user = _make_user(db_session, uid=104, scw=None)
    _make_allocation(db_session, user.id, "10000")
    db_session.commit()

    assert resolve_user_deposit_usd(db_session, user.id) == Decimal("10000")


def test_scw_user_proposal_sizing_uses_onchain_balance(db_session: Session) -> None:
    """提案サイジングもゲートと同じ規則で解決されること（両者の乖離を防ぐ）。

    乖離すると「実残高では通らない額の提案が生成され、承認時に初めて弾かれる」
    という無駄な期限切れを量産する。
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount

    user = _make_user(db_session, uid=105, scw=_SCW)
    _make_allocation(db_session, user.id, "4600")
    db_session.commit()

    # SCW 実残高 $1,000 → 10% = $100（帳簿 $4,600 の 10% = $460 ではない）
    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("1000"),
    ):
        amount = _resolve_proposal_amount(db_session, user.id)

    assert amount == Decimal("100.00")


def test_scw_user_below_minimum_deposit_is_skipped(db_session: Session) -> None:
    """SCW 実残高が最低入金額未満なら提案を作らない（帳簿があっても）。"""
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount

    user = _make_user(db_session, uid=106, scw=_SCW)
    _make_allocation(db_session, user.id, "4600")
    db_session.commit()

    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("50"),
    ):
        amount = _resolve_proposal_amount(db_session, user.id)

    assert amount == Decimal("0")
