# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_unreachable_approval_user_gate.py
"""受け入れ条件 B-6 の単体テスト（到達経路ゼロの承認型ユーザーに提案を作らない）。

承認型モードは「提案が本人に届き、本人が承認する」ことで初めて成立する。到達経路が
ゼロのまま提案を作り続けると誰にも見られないまま期限切れになり、承認率という指標を
「見られてすらいない母数」の上で計算することになる（本番で 25 日間・16 件・実行 0 件を
起こしたのがこの構造 / docs/internal/2026-08-04_usdt_switch_assessment_and_priorities.md）。

LINE 廃止後、エンドユーザーへの到達経路は Web Push のみ。本テストは
「配信側 (_deliver_ai_proposal_push) と同一基準で到達可否を判定する」ことを固定する。
判定基準がズレると、到達可能と判定したのに配信側で弾かれる新たな乖離が生まれる。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-unreachable-gate")

from app.auth.models import User  # noqa: E402
from app.automation import ai_judgment_scheduler as sched  # noqa: E402
from app.database import Base  # noqa: E402

_MOD = "app.automation.ai_judgment_scheduler"
# get_notification_service は関数内 import のため、モジュール属性ではなく import 元を差し替える。
_FACTORY = "app.notifications.factory.get_notification_service"


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


@pytest.fixture(autouse=True)
def _clear_alert_throttle() -> Generator[None, None, None]:
    """アラート絞り込みはプロセス内 dict なのでテスト間で持ち越さない。"""
    sched._unreachable_alerted_at.clear()
    yield
    sched._unreachable_alerted_at.clear()


def _make_user(
    db: Session,
    uid: int,
    *,
    execution_policy: str = "require_approval",
    push_enabled: bool = True,
) -> User:
    user = User(
        id=uid,
        email=f"unreach{uid}@test.com",
        username=f"unreach{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address="0x" + f"{uid:040x}",
        execution_policy=execution_policy,
        notification_settings_json=json.dumps({"push_enabled": push_enabled}),
    )
    db.add(user)
    db.flush()
    return user


class _FakeStore:
    """DatabaseSubscriptionStore の get_for_user だけを模した差し替え。"""

    def __init__(self, subs_by_user: dict[int, int]) -> None:
        self._subs_by_user = subs_by_user

    def __call__(self, _session_factory: object) -> "_FakeStore":
        return self

    def get_for_user(self, user_id: int) -> list[object]:
        return [object()] * self._subs_by_user.get(user_id, 0)


def _patch_push(subs_by_user: dict[int, int], *, vapid: bool = True) -> object:
    """push モジュールの依存を差し替えるコンテキストをまとめて返す。"""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch("app.notifications.push.get_vapid_config", return_value=object() if vapid else None)
    )
    stack.enter_context(
        patch("app.notifications.push.DatabaseSubscriptionStore", _FakeStore(subs_by_user))
    )
    return stack


class TestReachabilityDetection:
    def test_購読ゼロの承認型ユーザーはスキップされ運用者に通知される(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session, 501)
        with _patch_push({}), patch(f"{_MOD}._notify_unreachable_approval_user") as notify:
            assert sched._should_skip_unreachable_approval_user(db_session, user) is True
        notify.assert_called_once_with(501)

    def test_購読があれば提案生成は止まらない(self, db_session: Session) -> None:
        user = _make_user(db_session, 502)
        with _patch_push({502: 1}), patch(f"{_MOD}._notify_unreachable_approval_user") as notify:
            assert sched._should_skip_unreachable_approval_user(db_session, user) is False
        notify.assert_not_called()

    def test_通知設定OFFは購読があっても到達不能扱い(self, db_session: Session) -> None:
        """配信側 (push_allowed_for_user) と同一基準であることの確認。

        購読行だけを見て判定すると「設定画面では OFF なのに到達可能」とみなし、
        配信側で弾かれる提案を作り続けることになる。
        """
        user = _make_user(db_session, 503, push_enabled=False)
        with _patch_push({503: 1}):
            assert sched._user_has_reachable_channel(db_session, 503) is False
            assert sched._should_skip_unreachable_approval_user(db_session, user) is True

    def test_VAPID未設定は基盤障害であり提案生成を止めない(self, db_session: Session) -> None:
        """env 変数 1 つの設定ミスが「全承認型ユーザーの提案停止」に化けないこと。

        B-6 は *ユーザーごと* の到達経路の要件であり、配信基盤全体の障害とは別問題。
        ここを False に倒すと、防ごうとしている静かな故障より大きな故障を作る。
        基盤障害側は配信時に delivered=False として記録され到達率 (B-4) の急落で現れる。
        """
        user = _make_user(db_session, 504)
        with _patch_push({}, vapid=False):
            assert sched._user_has_reachable_channel(db_session, 504) is True
            assert sched._should_skip_unreachable_approval_user(db_session, user) is False


class TestScopeBoundaries:
    def test_AUTO_EXECUTEは到達経路ゼロでも対象外(self, db_session: Session) -> None:
        """おまかせ型は本人の承認を待たずに実行されるため通知が無くても価値を提供できる。

        ここを一緒に止めると、委譲枠を持つおまかせユーザーの運用まで巻き添えで停止する。
        """
        user = _make_user(db_session, 505, execution_policy="auto_execute")
        with _patch_push({}), patch(f"{_MOD}._notify_unreachable_approval_user") as notify:
            assert sched._should_skip_unreachable_approval_user(db_session, user) is False
        notify.assert_not_called()

    def test_判定が例外を投げても提案生成は止めない(self, db_session: Session) -> None:
        """可用性の後退を避ける: 判定の一時的な失敗が全ユーザーの提案停止に化けない。"""
        user = _make_user(db_session, 506)
        with (
            patch("app.notifications.push.get_vapid_config", side_effect=RuntimeError("boom")),
            patch(f"{_MOD}._notify_unreachable_approval_user") as notify,
        ):
            assert sched._should_skip_unreachable_approval_user(db_session, user) is False
        notify.assert_not_called()

    def test_購読が復活すれば自動的に再開する(self, db_session: Session) -> None:
        """B-6 の縮退は一方通行であってはならない（ユーザー操作だけで復帰できる）。"""
        user = _make_user(db_session, 507)
        with _patch_push({}), patch(f"{_MOD}._notify_unreachable_approval_user"):
            assert sched._should_skip_unreachable_approval_user(db_session, user) is True
        with _patch_push({507: 1}), patch(f"{_MOD}._notify_unreachable_approval_user"):
            assert sched._should_skip_unreachable_approval_user(db_session, user) is False


class TestAlertThrottling:
    def test_同一ユーザーへの連投は絞られる(self) -> None:
        """毎 tick 発火すると Slack を埋め尽くす（既存アラートが 14 日で 451 件出ていた）。"""
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            sched._notify_unreachable_approval_user(508)
            sched._notify_unreachable_approval_user(508)
            sched._notify_unreachable_approval_user(508)
        assert factory.call_count == 1

    def test_絞り込み期間を過ぎれば再送される(self) -> None:
        """恒久的に黙ると「対応漏れのまま忘れられる」ため、再送は残す。"""
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            sched._notify_unreachable_approval_user(509)
            sched._unreachable_alerted_at[509] = datetime.now(timezone.utc) - timedelta(
                hours=sched._UNREACHABLE_ALERT_INTERVAL_HOURS + 1
            )
            sched._notify_unreachable_approval_user(509)
        assert factory.call_count == 2

    def test_ユーザーごとに独立して絞られる(self) -> None:
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            sched._notify_unreachable_approval_user(510)
            sched._notify_unreachable_approval_user(511)
        assert factory.call_count == 2

    def test_通知送信が失敗しても例外を伝播しない(self) -> None:
        """best-effort: 通知の失敗が提案パイプラインを止めてはならない。"""
        with patch(_FACTORY, side_effect=RuntimeError("slack down")):
            sched._notify_unreachable_approval_user(512)  # 例外が出ないこと
