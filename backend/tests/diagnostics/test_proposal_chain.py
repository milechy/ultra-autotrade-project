"""app.diagnostics.proposal_chain (提案チェーン ゲートトレーサ) のテスト。"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.models import AIDecision, AiDecisionFeature
from app.auth.models import InvestmentTier, User
from app.database import Base
from app.diagnostics.proposal_chain import diagnose
from app.partner.allocation_models import FundAllocation
from app.proposals.models import Proposal


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _add_decision(session, action: str, *, indicator_conf: int = 86, macro_conf: int = 55):
    d = AIDecision(
        query="test",
        action=action,
        confidence=indicator_conf,
        primary_provider="claude",
        primary_action=action,
        primary_confidence=indicator_conf,
    )
    session.add(d)
    session.flush()
    feat = AiDecisionFeature(
        ai_decision_id=d.id,
        agent_signals=[
            {"name": "indicator", "bias": "bullish", "confidence": indicator_conf},
            {"name": "macro", "bias": "bullish", "confidence": macro_conf},
        ],
        judge_action=action,
        confidence=indicator_conf,
        cross_verify=False,
    )
    session.add(feat)
    session.flush()
    return d


def _add_user(session, *, policy="require_approval", tier=InvestmentTier.UPPER.value, funded=True):
    u = User(
        email=f"u{session.query(User).count()}@example.com",
        username=f"u{session.query(User).count()}",
        hashed_password="x",
        is_active=True,
        execution_policy=policy,
        tier=tier,
        last_judgment_at=None,
    )
    session.add(u)
    session.flush()
    if funded:
        session.add(
            FundAllocation(
                partner_id=u.id,
                tester_name=f"t-{u.id}",
                tester_user_id=u.id,
                allocated_amount_usd=Decimal("1000"),
                status="active",
            )
        )
        session.flush()
    return u


def _add_pending(session, user_id: int, *, expired: bool):
    now = datetime.now(timezone.utc)
    p = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("100"),
        amount_usd=Decimal("100"),
        reason="x",
        status="pending",
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=1),
    )
    session.add(p)
    session.flush()
    return p


def test_no_decision_verdict(db_session):
    """ai_decisions が空なら NO_DECISION。"""
    report = diagnose(db_session)
    assert report["verdict"].startswith("NO_DECISION")


def test_buy_with_funded_user_is_reachable(db_session):
    """BUY 判定 + funded/require_approval/pending なし → REACHABLE、当該ユーザーは受信可。"""
    _add_decision(db_session, "BUY")
    u = _add_user(db_session, funded=True)
    db_session.commit()

    report = diagnose(db_session)
    assert report["verdict"].startswith("REACHABLE")
    row = next(r for r in report["delivery_layer"]["users"] if r["user_id"] == u.id)
    assert row["would_receive_on_buy"] is True


def test_hold_decision_but_delivery_ready(db_session):
    """最新が HOLD でも、配信層が準備できていれば DECISION_HOLD として区別される。"""
    _add_decision(db_session, "HOLD")
    _add_user(db_session, funded=True)
    db_session.commit()

    report = diagnose(db_session)
    assert report["verdict"].startswith("DECISION_HOLD")
    assert report["delivery_layer"]["deliverable_on_buy"] == 1


def test_fresh_pending_blocks_but_stale_does_not(db_session):
    """期限内 pending は配信をブロックし、期限切れ pending はブロックしないこと。"""
    _add_decision(db_session, "BUY")
    blocked = _add_user(db_session, funded=True)
    ok = _add_user(db_session, funded=True)
    _add_pending(db_session, blocked.id, expired=False)  # 期限内 → ブロック
    _add_pending(db_session, ok.id, expired=True)  # 期限切れ → ブロックしない
    db_session.commit()

    report = diagnose(db_session)
    rows = {r["user_id"]: r for r in report["delivery_layer"]["users"]}
    assert rows[blocked.id]["would_receive_on_buy"] is False
    assert any("blocking_pending" in b for b in rows[blocked.id]["blockers"])
    assert rows[ok.id]["would_receive_on_buy"] is True
    assert rows[ok.id]["pending_stale"] == 1


def test_unfunded_and_wrong_policy_are_blocked(db_session):
    """未funded と auto_execute(require_approval でない) は受信不可としてブロッカーに出る。"""
    _add_decision(db_session, "BUY")
    unfunded = _add_user(db_session, funded=False)
    auto = _add_user(db_session, policy="auto_execute", funded=True)
    db_session.commit()

    report = diagnose(db_session)
    rows = {r["user_id"]: r for r in report["delivery_layer"]["users"]}
    assert rows[unfunded.id]["would_receive_on_buy"] is False
    assert any("not_funded" in b for b in rows[unfunded.id]["blockers"])
    assert rows[auto.id]["would_receive_on_buy"] is False
    assert any("policy=auto_execute" in b for b in rows[auto.id]["blockers"])
