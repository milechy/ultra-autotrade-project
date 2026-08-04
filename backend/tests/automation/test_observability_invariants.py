# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_observability_invariants.py
"""_check_observability_invariants の単体テスト（2026-08-04 PR1: 可観測性の確立）。

25日間、委譲枠欠如も通知の失敗も警告ログに残るだけで誰にも気づかれなかった
(docs/internal/2026-08-04_usdt_switch_assessment_and_priorities.md)。本テストは
「検知した時点で必ず運営(Slack)へ通知される」ことと、既存の提案生成ロジックへ
副作用が無いことを検証する。
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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-observability-invariants")

from app.auth.models import User  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _PROPOSAL_EXPIRES_HOURS,
    _check_observability_invariants,
)
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


def _make_user(db: Session, uid: int, execution_policy: str = "auto_execute") -> User:
    user = User(
        id=uid,
        email=f"obsinv{uid}@test.com",
        username=f"obsinv{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address=_wallet_for(uid),
        execution_policy=execution_policy,
    )
    db.add(user)
    db.flush()
    return user


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


def _make_proposal(db: Session, user_id: int, status: str, created_at: datetime) -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        protocol="aave",
        amount=Decimal("100"),
        amount_usd=Decimal("100.00"),
        reason="obs invariant test",
        status=status,
        expires_at=created_at + timedelta(hours=_PROPOSAL_EXPIRES_HOURS),
        created_at=created_at,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _sent_messages(db: Session, user: User) -> list[object]:
    sent: list[object] = []
    with patch(
        "app.notifications.factory.get_notification_service",
        return_value=type("Svc", (), {"send": lambda self, msg: sent.append(msg)})(),
    ):
        _check_observability_invariants(db, user)
    return sent


def test_proposal_expires_hours_is_168() -> None:
    """72h → 168h(1週間) への変更 (到達経路が無い現状での短すぎる期限を是正)。"""
    assert _PROPOSAL_EXPIRES_HOURS == 168


class TestMissingDelegationGrant:
    def test_auto_execute_with_active_grant_no_notification(self, db_session: Session) -> None:
        user = _make_user(db_session, uid=101, execution_policy="auto_execute")
        _make_grant(db_session, user.id)
        db_session.commit()

        assert _sent_messages(db_session, user) == []

    def test_auto_execute_without_grant_notifies_once(self, db_session: Session) -> None:
        user = _make_user(db_session, uid=102, execution_policy="auto_execute")
        db_session.commit()

        sent = _sent_messages(db_session, user)
        assert len(sent) == 1
        assert sent[0].channel.value == "slack"
        assert str(user.id) in sent[0].body

    def test_auto_execute_with_expired_grant_notifies_once(self, db_session: Session) -> None:
        """status='active' のまま expires_at が過去 (遅延 expire) でも実時刻で再判定して検知する。"""
        user = _make_user(db_session, uid=103, execution_policy="auto_execute")
        _make_grant(
            db_session,
            user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db_session.commit()

        sent = _sent_messages(db_session, user)
        assert len(sent) == 1

    def test_auto_execute_grant_expires_soon_no_notification(self, db_session: Session) -> None:
        """境界値: expires_at が僅かに未来 (1秒後) ならまだ有効 → 通知なし。"""
        user = _make_user(db_session, uid=104, execution_policy="auto_execute")
        _make_grant(
            db_session,
            user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=5),
        )
        db_session.commit()

        assert _sent_messages(db_session, user) == []

    def test_require_approval_user_not_checked(self, db_session: Session) -> None:
        """REQUIRE_APPROVAL ユーザーは委譲grant不変条件の対象外 (grantなしでも通知なし)。"""
        user = _make_user(db_session, uid=105, execution_policy="require_approval")
        db_session.commit()

        assert _sent_messages(db_session, user) == []


class TestConsecutiveExpiry:
    def _make_canceled_chain(
        self, db: Session, user: User, count: int, *, non_canceled_first: bool = False
    ) -> None:
        now = datetime.now(timezone.utc)
        for i in range(count):
            status = "canceled"
            if non_canceled_first and i == 0:
                status = "pending"
            _make_proposal(db, user.id, status, now - timedelta(days=count - i))

    def test_two_consecutive_canceled_no_notification(self, db_session: Session) -> None:
        user = _make_user(db_session, uid=201, execution_policy="require_approval")
        self._make_canceled_chain(db_session, user, 2)
        db_session.commit()

        assert _sent_messages(db_session, user) == []

    def test_three_consecutive_canceled_notifies_once(self, db_session: Session) -> None:
        user = _make_user(db_session, uid=202, execution_policy="require_approval")
        self._make_canceled_chain(db_session, user, 3)
        db_session.commit()

        sent = _sent_messages(db_session, user)
        assert len(sent) == 1
        assert "3" in sent[0].body

    def test_four_consecutive_canceled_notifies_once(self, db_session: Session) -> None:
        user = _make_user(db_session, uid=203, execution_policy="require_approval")
        self._make_canceled_chain(db_session, user, 4)
        db_session.commit()

        sent = _sent_messages(db_session, user)
        assert len(sent) == 1

    def test_non_canceled_most_recent_breaks_streak(self, db_session: Session) -> None:
        """直近3件のうち1件でも canceled でなければ (=承認/実行された) 通知しない。"""
        user = _make_user(db_session, uid=204, execution_policy="require_approval")
        now = datetime.now(timezone.utc)
        _make_proposal(db_session, user.id, "canceled", now - timedelta(days=3))
        _make_proposal(db_session, user.id, "canceled", now - timedelta(days=2))
        _make_proposal(db_session, user.id, "executed", now - timedelta(days=1))
        db_session.commit()

        assert _sent_messages(db_session, user) == []


def test_no_side_effect_on_proposal_or_grant_rows(db_session: Session) -> None:
    """検知と通知のみ: 呼び出しが Proposal/DelegationGrant のどの行も書き換えない。"""
    user = _make_user(db_session, uid=301, execution_policy="auto_execute")
    now = datetime.now(timezone.utc)
    _make_proposal(db_session, user.id, "canceled", now - timedelta(days=3))
    _make_proposal(db_session, user.id, "canceled", now - timedelta(days=2))
    _make_proposal(db_session, user.id, "canceled", now - timedelta(days=1))
    db_session.commit()

    _check_observability_invariants(db_session, user)

    proposals = db_session.query(Proposal).filter(Proposal.user_id == user.id).all()
    assert all(p.status == "canceled" for p in proposals)
    assert db_session.query(DelegationGrant).filter(DelegationGrant.user_id == user.id).count() == 0
