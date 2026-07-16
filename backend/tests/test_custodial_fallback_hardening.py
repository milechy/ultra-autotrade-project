# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_custodial_fallback_hardening.py
"""_execute_aave_for_proposal の custodial fallback ハードニング（2026-07-16 Step 0.5）。

有効な委譲(SCW) grant を持つユーザーの操作が _should_use_scw_route で対象外
（例: WITHDRAW は常に custodial 扱い対象外）と判定された場合に、サーバー単一鍵
(AAVE_WALLET_PRIVATE_KEY) の custodial 経路へ暗黙に落とさないことを検証する。
grant が無い（従来の custodial ファンドプールユーザー）場合は従来どおり custodial
経路が使われることも合わせて確認する。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-custodial-fallback")

from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.models import User  # noqa: E402
from app.automation.safety_gate import HardStopResult  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

_WALLET = "0xCustodialFallback00000000000000000000001"


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


def _make_user(db: Session, uid: int = 21) -> User:
    user = User(
        id=uid,
        email=f"custodialfallback{uid}@test.com",
        username=f"custodialfallback{uid}",
        hashed_password="x",
        role="partner",
        is_active=True,
        wallet_address=_WALLET,
    )
    db.add(user)
    db.flush()
    return user


def _make_proposal(db: Session, user_id: int, operation: str = "WITHDRAW") -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        operation=operation,
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="custodial fallback hardening test",
        status="approved",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    return proposal


def _fake_result() -> AaveOperationResult:
    return AaveOperationResult(
        operation=AaveOperationType.WITHDRAW,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000"),
        tx_hash="0xexec",
    )


def _grant() -> SimpleNamespace:
    return SimpleNamespace(
        wallet_address="0xSCW", privy_signer_id="s1", privy_policy_id="p1", allowed_protocols=[]
    )


def test_grant_present_but_scw_ineligible_does_not_fall_back_to_custodial(
    db_session: Session,
) -> None:
    """grant あり + WITHDRAW（_should_use_scw_route=False）→ custodial 経路(execute_rebalance)
    を呼ばず、status='approved' のまま据え置く（HARD_STOP/risk_limiter と同じ transient 扱い）。
    """
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id, operation="WITHDRAW")
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return _fake_result()

    with (
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch("app.proposals.router.get_active_grant", return_value=_grant()),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == []  # custodial 単一鍵経路は呼ばれない
    assert proposal.status == "approved"  # transient: failed にも executed にもしない
    assert proposal.tx_hash is None


def test_no_grant_still_uses_custodial_path(db_session: Session) -> None:
    """grant が存在しない（従来の custodial ファンドプールユーザー）場合は
    引き続き custodial 経路(execute_rebalance)が使われ、挙動が変わらないことを確認する。
    """
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session, uid=22)
    proposal = _make_proposal(db_session, user_id=user.id, operation="SUPPLY")
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol="USDC",
            amount=Decimal("1000"),
            tx_hash="0xexec",
        )

    with (
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch("app.proposals.router.get_active_grant", return_value=None),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == [True]
    assert proposal.status == "executed"
    assert proposal.tx_hash == "0xexec"
