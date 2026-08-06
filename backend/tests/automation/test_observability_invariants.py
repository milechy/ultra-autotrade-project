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
        # 2026-08-06 PR6: 運用者向け Slack 通知に加えて本人向け降格通知も送るため、
        # 「運用者向けが1件あること」を検証する (総数ではなく種別で見る)。
        ops = [
            m
            for m in sent
            if m.channel.value == "slack" and "有効な委譲枠がありません" in str(m.title)
        ]
        assert len(ops) == 1, f"委譲枠欠如の運用者向け通知が1件でない: {sent}"

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
        # 2026-08-06 PR6: 本人向け降格通知が増えたため、運用者向けが1件あることで検証する。
        ops = [
            m
            for m in sent
            if m.channel.value == "slack" and "有効な委譲枠がありません" in str(m.title)
        ]
        assert len(ops) == 1, f"委譲枠欠如の運用者向け通知が1件でない: {sent}"

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


class TestDowngradeOrphanedAutoExecute:
    """実行権限を持たない AUTO_EXECUTE ユーザーの安全側降格 (2026-08-06 PR6)。

    PR1 (#1011) が「検知のみで降格は行わない (降格は PR6)」としていた部分の実装。
    要件定義 A-E1「黙って承認待ちに落とさない。検知・通知・安全側降格」/
    A-6「権限失効時に安全側へ降格し、ユーザーに通知される」に対応する。

    順序の制約 (IV-2 / 禁止事項7): 降格は到達経路 (Web Push) 復旧後にのみ許される。
    通知できない状態で降格すると「無断で設定が変わった」としか映らないため。
    """

    def test_orphaned_auto_execute_is_downgraded(self, db_session: Session) -> None:
        """★委譲枠を持たない AUTO_EXECUTE は require_approval へ降格される。"""
        user = _make_user(db_session, uid=301, execution_policy="auto_execute")
        db_session.commit()

        _sent_messages(db_session, user)
        db_session.commit()  # 本番では per-user savepoint 経由で commit される

        db_session.refresh(user)
        assert user.execution_policy == "require_approval"

    def test_downgrade_notifies_the_user_not_only_ops(self, db_session: Session) -> None:
        """★運用者向け Slack だけでなく、本人宛の通知も送られること。

        「黙って承認待ちに落とさない」(A-E1) の核心。運用者だけが知っていて
        ユーザーが知らない状態は、表示と実態の乖離を別の形で再生産する。
        """
        user = _make_user(db_session, uid=302, execution_policy="auto_execute")
        db_session.commit()

        sent = _sent_messages(db_session, user)

        user_addressed = [m for m in sent if getattr(m, "user_id", None) == user.id]
        assert user_addressed, f"本人宛の通知が無い: {[getattr(m, 'title', m) for m in sent]}"
        body = " ".join(str(getattr(m, "body", "")) for m in user_addressed)
        # 何が起きたか / 資産への影響 / 元に戻す方法 が伝わること (IV-2)
        assert "承認制" in body, f"何に変わったかが伝わらない: {body}"
        assert "資産" in body, f"資産への影響の有無が伝わらない: {body}"

    def test_user_with_valid_grant_is_not_downgraded(self, db_session: Session) -> None:
        """有効な委譲枠を持つユーザーは降格されない (正常な完全おまかせを壊さない)。"""
        user = _make_user(db_session, uid=303, execution_policy="auto_execute")
        _make_grant(db_session, user.id)
        db_session.commit()

        _sent_messages(db_session, user)
        db_session.commit()

        db_session.refresh(user)
        assert user.execution_policy == "auto_execute", "正常なおまかせを降格してはいけない"

    def test_require_approval_user_is_untouched(self, db_session: Session) -> None:
        """元から承認制のユーザーには何も起きない。"""
        user = _make_user(db_session, uid=304, execution_policy="require_approval")
        db_session.commit()

        _sent_messages(db_session, user)
        db_session.commit()

        db_session.refresh(user)
        assert user.execution_policy == "require_approval"

    def test_downgrade_is_idempotent(self, db_session: Session) -> None:
        """2回目以降の tick で重複して降格・通知しないこと。

        降格後は execution_policy が require_approval になるため、次回以降は
        そもそも検知条件に入らない (60秒ごとに通知が飛び続けない)。
        """
        user = _make_user(db_session, uid=305, execution_policy="auto_execute")
        db_session.commit()

        first = _sent_messages(db_session, user)
        db_session.commit()
        second = _sent_messages(db_session, user)

        assert len(first) >= 1
        assert second == [], f"降格後も通知が続いている: {second}"

    def test_notification_failure_does_not_block_downgrade(self, db_session: Session) -> None:
        """通知が失敗しても降格自体は確定すること。

        通知失敗を理由に危険側 (auto_execute) へ留めるべきではない。
        """
        user = _make_user(db_session, uid=306, execution_policy="auto_execute")
        db_session.commit()

        def _boom(self, msg):  # noqa: ANN001, ANN202
            raise RuntimeError("notification backend down")

        with patch(
            "app.notifications.factory.get_notification_service",
            return_value=type("Svc", (), {"send": _boom})(),
        ):
            _check_observability_invariants(db_session, user)
        db_session.commit()

        db_session.refresh(user)
        assert user.execution_policy == "require_approval", "通知失敗で降格が巻き戻っている"


class TestUnreachableUserDetection:
    """降格通知がユーザーに届かない場合の検知 (2026-08-06)。

    本番で実際に起きた問題: user 11/18 を承認制へ降格したが、両名とも Push を
    購読しておらず通知は届かなかった。しかし「届かなかった」事実はどこにも
    記録されず、運用者も気づけなかった。

    要件定義 IV-2 の「通知できない状態で降格するな」は、**仕組みが動くこと**では
    なく**そのユーザーに実際に届くこと**で判定しなければならない。
    """

    def test_unreachable_user_triggers_ops_escalation(self, db_session: Session) -> None:
        """★到達経路が無いユーザーを降格したら運用者へエスカレーションすること。"""
        user = _make_user(db_session, uid=401, execution_policy="auto_execute")
        # notification_settings_json 未設定 = push_enabled 既定 False = 到達経路ゼロ
        db_session.commit()

        sent = _sent_messages(db_session, user)

        titles = [str(getattr(m, "title", "")) for m in sent]
        assert any("届いていません" in t for t in titles), (
            f"未到達のエスカレーションが無い: {titles}"
        )

    def test_reachable_user_does_not_trigger_escalation(self, db_session: Session) -> None:
        """到達できるユーザーでは未到達エスカレーションを出さないこと (誤検知防止)。"""
        import json
        from unittest.mock import patch as _patch

        user = _make_user(db_session, uid=402, execution_policy="auto_execute")
        user.notification_settings_json = json.dumps(
            {"push_enabled": True, "preferences": {"system_notice": True}}
        )
        db_session.commit()

        sent: list[object] = []
        with (
            _patch(
                "app.notifications.factory.get_notification_service",
                return_value=type("Svc", (), {"send": lambda self, msg: sent.append(msg)})(),
            ),
            # 実際に到達したことにする
            _patch(
                "app.automation.ai_judgment_scheduler._deliver_ai_proposal_push",
                return_value=True,
            ),
        ):
            _check_observability_invariants(db_session, user)

        titles = [str(getattr(m, "title", "")) for m in sent]
        assert not any("届いていません" in t for t in titles), (
            f"到達しているのに未到達扱いになっている: {titles}"
        )

    def test_undelivered_push_is_recorded_for_reachability_metric(
        self, db_session: Session
    ) -> None:
        """★未到達も notification_logs に delivered=False で記録されること。

        記録しないと到達率 (受け入れ条件 B-4) が「送れたものだけ」を母数に
        計算され、実態より良く見えてしまう。
        """
        from app.notifications.models import NotificationLog

        user = _make_user(db_session, uid=403, execution_policy="auto_execute")
        db_session.commit()

        _sent_messages(db_session, user)
        db_session.commit()

        rows = (
            db_session.query(NotificationLog)
            .filter(NotificationLog.user_id == user.id, NotificationLog.channel == "push")
            .all()
        )
        assert rows, "未到達が push チャネルの行として記録されていない"
        assert all(r.delivered is False for r in rows), (
            f"未到達なのに delivered が False でない: {[r.delivered for r in rows]}"
        )
