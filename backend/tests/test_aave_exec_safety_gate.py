# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_aave_exec_safety_gate.py
"""_execute_aave_for_proposal の HARD_STOP 安全ゲート（スライス0-E2）。

execute 直前に safety_gate.evaluate_hard_stop を通し、blocked のとき execute_rebalance を
呼ばず proposal を 'approved' のまま据え置く（transient なので dead-letter しない）ことを検証。
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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-exec-gate")

from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.models import User  # noqa: E402
from app.automation.safety_gate import HardStopResult  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

_WALLET = "0xExecGate0000000000000000000000000000000001"


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


def _make_user(db: Session, uid: int = 11) -> User:
    user = User(
        id=uid,
        email=f"execgate{uid}@test.com",
        username=f"execgate{uid}",
        hashed_password="x",
        role="partner",
        is_active=True,
        wallet_address=_WALLET,
    )
    db.add(user)
    db.flush()
    return user


def _make_proposal(db: Session, user_id: int) -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="exec safety gate test",
        status="approved",
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
        amount=Decimal("1000"),
        tx_hash="0xexec",
    )


def test_hard_stop_holds_execution(db_session: Session) -> None:
    """HARD_STOP 発火時は execute_rebalance を呼ばず status を 'approved' のまま据え置く。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return _fake_result()

    with (
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(
                blocked=True, reason="emergency_stop", source="rule_engine"
            ),
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == []  # execute_rebalance は呼ばれない
    assert proposal.status == "approved"  # transient: failed にしない
    assert proposal.tx_hash is None


def test_no_hard_stop_allows_execution(db_session: Session) -> None:
    """HARD_STOP 非発火時は従来通り execute_rebalance まで進み executed になる。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
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
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == [True]  # execute_rebalance が呼ばれる
    assert proposal.status == "executed"
    assert proposal.tx_hash == "0xexec"
