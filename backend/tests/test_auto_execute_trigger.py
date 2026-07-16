# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_auto_execute_trigger.py
"""run_auto_execution_for_ai_decision の単体テスト（2026-07-16「完全おまかせ」配線）。

AUTO_EXECUTE ユーザーの pending proposal のうち、有効な委譲(SCW) grant を持つ分だけを
即時実行し、それ以外（grant なし / WITHDRAW 等 SCW 非対応 operation）は 'pending' の
まま custodial 単一鍵経路へ絶対に落とさないことを検証する（Step 0.5 の安全境界の
scheduler 側での再確認）。HARD_STOP 等の transient ゲートも通ることを確認する。
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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-auto-execute-trigger")

from app.ai.models import AIDecision  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.automation.safety_gate import HardStopResult  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402
from app.users.models import DelegationGrant  # noqa: E402


def _wallet_for(uid: int) -> str:
    return "0x" + f"{uid:040x}"


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


@pytest.fixture()
def enabled_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("DELEGATION_PRIVY_POLICY_ENABLED", "true")
    monkeypatch.setenv("PRIVY_SERVER_SIGNER_ID", "kq_server_1")
    monkeypatch.setenv("PRIVY_APP_ID", "app123")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret123")
    monkeypatch.setenv("AUTO_EXECUTION_ENABLED", "true")
    yield


def _make_user(db: Session, uid: int, execution_policy: str = "auto_execute") -> User:
    user = User(
        id=uid,
        email=f"autoexec{uid}@test.com",
        username=f"autoexec{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address=_wallet_for(uid),
        execution_policy=execution_policy,
    )
    db.add(user)
    db.flush()
    return user


def _make_decision(db: Session, decision_id: int = 1) -> AIDecision:
    decision = AIDecision(
        id=decision_id,
        query="q",
        action="BUY",
        confidence=80,
        primary_provider="claude",
        primary_action="BUY",
        primary_confidence=80,
    )
    db.add(decision)
    db.flush()
    return decision


def _make_proposal(
    db: Session, user_id: int, decision_id: int, operation: str = "SUPPLY"
) -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        ai_decision_id=decision_id,
        operation=operation,
        asset="USDC",
        protocol="aave",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="auto execute trigger test",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    return proposal


def _make_grant(db: Session, user_id: int, **overrides: object) -> DelegationGrant:
    now = datetime.now(timezone.utc)
    defaults: dict[str, object] = dict(
        user_id=user_id,
        wallet_address="0xSCW",
        status="active",
        max_single_trade_pct=Decimal("10"),
        max_daily_trade_pct=Decimal("30"),
        hf_floor=Decimal("1.6"),
        allowed_protocols=["aave"],
        allowed_assets=["USDC"],
        privy_signer_id="s1",
        privy_policy_id="p1",
        consent_at=now,
        expires_at=now + timedelta(days=30),
    )
    defaults.update(overrides)
    grant = DelegationGrant(**defaults)
    db.add(grant)
    db.flush()
    return grant


def test_no_grant_stays_pending_and_is_skipped(db_session: Session, enabled_env: None) -> None:
    """委譲grantが無いAUTO_EXECUTEユーザーの提案は実行されず 'pending' のまま。"""
    from app.proposals.auto_execute import run_auto_execution_for_ai_decision

    user = _make_user(db_session, uid=1)
    decision = _make_decision(db_session)
    proposal = _make_proposal(db_session, user.id, decision.id)
    db_session.commit()

    with patch("app.aave.service.MultiChainAaveService.execute_rebalance") as mock_execute:
        result = run_auto_execution_for_ai_decision(db_session, decision.id)

    mock_execute.assert_not_called()
    assert result == {"auto_executed": 0, "auto_execute_skipped": 1, "auto_execute_failed": 0}
    db_session.refresh(proposal)
    assert proposal.status == "pending"


def test_grant_with_supply_executes_via_scw(db_session: Session, enabled_env: None) -> None:
    """SCW 対象(SUPPLY)+有効grant → 委譲経路で即時実行され 'executed' になる。"""
    from app.proposals.auto_execute import run_auto_execution_for_ai_decision
    from app.proposals.scw_executor import ScwExecutionResult

    user = _make_user(db_session, uid=2)
    decision = _make_decision(db_session)
    proposal = _make_proposal(db_session, user.id, decision.id, operation="SUPPLY")
    _make_grant(db_session, user.id)
    db_session.commit()

    fake_client = type(
        "FakeClient",
        (),
        {
            "build_deposit_txs": lambda self, *a, **kw: {
                "approve_tx": {"to": "0xtoken", "data": "0xa", "value": "0x0"},
                "supply_tx": {"to": "0xpool", "data": "0xs", "value": "0x0"},
            }
        },
    )()
    fake_service = type(
        "FakeService",
        (),
        {"get_service": lambda self, chain: type("S", (), {"client": fake_client})()},
    )()

    with (
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch("app.aave.service.MultiChainAaveService", lambda: fake_service),
        patch(
            "app.proposals.scw_executor.execute_calls_via_scw",
            return_value=ScwExecutionResult(tx_hash="0xauto1", status="submitted", raw={}),
        ),
    ):
        result = run_auto_execution_for_ai_decision(db_session, decision.id)

    assert result == {"auto_executed": 1, "auto_execute_skipped": 0, "auto_execute_failed": 0}
    db_session.refresh(proposal)
    assert proposal.status == "executed"
    assert proposal.tx_hash == "0xauto1"


def test_grant_with_withdraw_never_falls_back_to_custodial(
    db_session: Session, enabled_env: None
) -> None:
    """有効grantがあってもWITHDRAWはSCW対象外 → custodial単一鍵経路に絶対に落ちず
    'pending' のまま skip される（Step 0.5 の安全境界の scheduler 側再確認）。"""
    from app.proposals.auto_execute import run_auto_execution_for_ai_decision

    user = _make_user(db_session, uid=3)
    decision = _make_decision(db_session)
    proposal = _make_proposal(db_session, user.id, decision.id, operation="WITHDRAW")
    _make_grant(db_session, user.id)
    db_session.commit()

    with patch("app.aave.service.MultiChainAaveService.execute_rebalance") as mock_execute:
        result = run_auto_execution_for_ai_decision(db_session, decision.id)

    mock_execute.assert_not_called()
    assert result == {"auto_executed": 0, "auto_execute_skipped": 1, "auto_execute_failed": 0}
    db_session.refresh(proposal)
    assert proposal.status == "pending"


def test_hard_stop_holds_as_approved_transient(db_session: Session, enabled_env: None) -> None:
    """HARD_STOP発火時は執行を待避し 'approved' のまま据え置く（transient・再試行可能）。"""
    from app.proposals.auto_execute import run_auto_execution_for_ai_decision

    user = _make_user(db_session, uid=4)
    decision = _make_decision(db_session)
    proposal = _make_proposal(db_session, user.id, decision.id, operation="SUPPLY")
    _make_grant(db_session, user.id)
    db_session.commit()

    with patch(
        "app.automation.safety_gate.evaluate_hard_stop",
        return_value=HardStopResult(blocked=True, reason="emergency_stop", source="rule_engine"),
    ):
        result = run_auto_execution_for_ai_decision(db_session, decision.id)

    assert result == {"auto_executed": 1, "auto_execute_skipped": 0, "auto_execute_failed": 0}
    db_session.refresh(proposal)
    assert proposal.status == "approved"
    assert proposal.tx_hash is None


def test_one_proposal_failure_does_not_stop_others(db_session: Session, enabled_env: None) -> None:
    """1件の未想定例外が他のAUTO_EXECUTE proposalの処理を止めない。"""
    from app.proposals.auto_execute import run_auto_execution_for_ai_decision

    user1 = _make_user(db_session, uid=5)
    user2 = _make_user(db_session, uid=6)
    decision = _make_decision(db_session)
    p1 = _make_proposal(db_session, user1.id, decision.id, operation="SUPPLY")
    p2 = _make_proposal(db_session, user2.id, decision.id, operation="SUPPLY")
    _make_grant(db_session, user1.id)
    # user2 には grant を与えない -> skip されるだけで例外にはならないが、
    # get_active_grant 自体が例外を投げるケースを模してロバスト性を検証する。
    db_session.commit()

    call_count = {"n": 0}
    real_get_active_grant = __import__(
        "app.users.models", fromlist=["get_active_grant"]
    ).get_active_grant

    def flaky_get_active_grant(user_id: int, db: Session):
        call_count["n"] += 1
        if user_id == user1.id:
            raise RuntimeError("simulated DB error for user1")
        return real_get_active_grant(user_id, db)

    with patch("app.proposals.auto_execute.get_active_grant", side_effect=flaky_get_active_grant):
        result = run_auto_execution_for_ai_decision(db_session, decision.id)

    assert result["auto_execute_failed"] == 1
    assert result["auto_execute_skipped"] == 1
    db_session.refresh(p1)
    db_session.refresh(p2)
    assert p1.status == "pending"  # user1 は例外 -> savepoint rollback で pending のまま
    assert p2.status == "pending"  # user2 は grant なし -> skip
