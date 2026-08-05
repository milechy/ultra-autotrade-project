# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/notifications/test_push_subscription_store.py
"""DatabaseSubscriptionStore の単体テスト（Web Push購読の永続化）。

InMemorySubscriptionStore は「メモリ保持・ユーザー未紐付け・認証なし」で、
再起動で全消失し誰の購読か分からなかった
(docs/internal/2026-08-04_execution_pipeline_requirements.md)。
本テストは DB 永続化・user_id 紐付け・複数ユーザー分離を検証する。

2026-08-05: 保存先を users.notification_settings_json の JSON 配列から
push_subscriptions テーブルへ変更した。アサーションは行ベースに書き換えている
(検証意図は同一)。endpoint のグローバル一意性は UNIQUE 制約が保証するため、
「他ユーザーから除去されること」はアプリロジックではなく制約の検証になった。
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-push-subscription-store")

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.notifications.push import DatabaseSubscriptionStore, WebPushSubscription  # noqa: E402


def _wallet_for(uid: int) -> str:
    return "0x" + f"{uid:040x}"


@pytest.fixture()
def _db_env() -> Generator[tuple[Session, "sessionmaker[Session]"], None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestSessionLocal()
    try:
        yield db, TestSessionLocal
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


@pytest.fixture()
def db_session(_db_env: tuple[Session, "sessionmaker[Session]"]) -> Session:
    """テストのセットアップ・アサーション専用セッション。"""
    return _db_env[0]


@pytest.fixture()
def session_factory(_db_env: tuple[Session, "sessionmaker[Session]"]):
    """呼ぶたびに新しい Session を返す (本番の SessionLocal と同じ挙動)。

    DatabaseSubscriptionStore は各操作の最後に db.close() する。db_session と
    同一オブジェクトを返すと commit/close で expire・detach され、以降の
    db_session 経由のアサーションが DetachedInstanceError になるため、
    同じ sqlite ファイルを指す別セッションを毎回払い出す。
    """
    _, TestSessionLocal = _db_env
    return TestSessionLocal


def _make_user(db: Session, uid: int, notification_settings_json: str | None = None) -> User:
    user = User(
        id=uid,
        email=f"pushstore{uid}@test.com",
        username=f"pushstore{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address=_wallet_for(uid),
        notification_settings_json=notification_settings_json,
    )
    db.add(user)
    db.flush()
    return user


class TestAddAndPersist:
    def test_add_persists_and_is_tied_to_user(self, db_session: Session, session_factory) -> None:
        user = _make_user(db_session, 401)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)

        store.add(
            WebPushSubscription(
                endpoint="https://push.example.com/ep1", p256dh="k1", auth="a1", user_id=user.id
            )
        )

        rows = store.get_for_user(user.id)
        assert [(r.endpoint, r.p256dh, r.auth) for r in rows] == [
            ("https://push.example.com/ep1", "k1", "a1")
        ]

    def test_add_without_user_id_is_noop(self, db_session: Session, session_factory) -> None:
        store = DatabaseSubscriptionStore(session_factory)
        store.add(
            WebPushSubscription(endpoint="https://push.example.com/ep2", p256dh="k", auth="a")
        )
        assert store.count() == 0

    def test_add_does_not_touch_notification_settings(
        self, db_session: Session, session_factory
    ) -> None:
        """購読保存が通知設定 (別ストレージ) を一切変更しないこと。

        以前は同一 JSON セルを共有しており、双方の read-modify-write が
        互いを踏んで lost update を起こしていた。テーブル分離後は構造的に干渉しない。
        """
        existing = json.dumps({"line_enabled": False, "push_enabled": True, "preferences": {}})
        user = _make_user(db_session, 402, notification_settings_json=existing)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)

        store.add(
            WebPushSubscription(
                endpoint="https://push.example.com/ep3", p256dh="k", auth="a", user_id=user.id
            )
        )

        db_session.refresh(user)
        assert user.notification_settings_json == existing, "通知設定は 1 バイトも変わらないこと"
        assert len(store.get_for_user(user.id)) == 1

    def test_add_same_endpoint_removes_from_other_user(
        self, db_session: Session, session_factory
    ) -> None:
        """同一端末での再ログイン等 (I-5/I-12): endpoint はグローバル一意。"""
        user_a = _make_user(db_session, 403)
        user_b = _make_user(db_session, 404)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        endpoint = "https://push.example.com/shared-device"

        store.add(WebPushSubscription(endpoint=endpoint, p256dh="k1", auth="a1", user_id=user_a.id))
        store.add(WebPushSubscription(endpoint=endpoint, p256dh="k2", auth="a2", user_id=user_b.id))

        assert store.get_for_user(user_a.id) == [], "旧ユーザーから除去されること"
        b_subs = store.get_for_user(user_b.id)
        assert len(b_subs) == 1
        assert b_subs[0].p256dh == "k2"
        assert store.count() == 1, "endpoint は UNIQUE なので全体で 1 行"

    def test_add_duplicate_endpoint_same_user_overwrites(
        self, db_session: Session, session_factory
    ) -> None:
        user = _make_user(db_session, 405)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        endpoint = "https://push.example.com/ep-dup"

        store.add(WebPushSubscription(endpoint=endpoint, p256dh="k1", auth="a1", user_id=user.id))
        store.add(WebPushSubscription(endpoint=endpoint, p256dh="k2", auth="a2", user_id=user.id))

        subs = store.get_for_user(user.id)
        assert len(subs) == 1
        assert subs[0].p256dh == "k2"


class TestRemove:
    def test_remove_deletes_from_owning_user(self, db_session: Session, session_factory) -> None:
        user = _make_user(db_session, 406)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        endpoint = "https://push.example.com/ep-remove"
        store.add(WebPushSubscription(endpoint=endpoint, p256dh="k", auth="a", user_id=user.id))

        store.remove(endpoint)

        assert store.get_for_user(user.id) == []

    def test_remove_nonexistent_endpoint_is_noop(
        self, db_session: Session, session_factory
    ) -> None:
        store = DatabaseSubscriptionStore(session_factory)
        store.remove("https://push.example.com/does-not-exist")  # should not raise


class TestGetAllAndGetForUser:
    def test_get_all_aggregates_across_users(self, db_session: Session, session_factory) -> None:
        user1 = _make_user(db_session, 407)
        user2 = _make_user(db_session, 408)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/1", p256dh="k1", auth="a1", user_id=user1.id
            )
        )
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/2", p256dh="k2", auth="a2", user_id=user2.id
            )
        )
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/3", p256dh="k3", auth="a3", user_id=user1.id
            )
        )

        all_subs = store.get_all()
        assert store.count() == 3
        endpoints = {s.endpoint for s in all_subs}
        assert endpoints == {
            "https://p.example.com/1",
            "https://p.example.com/2",
            "https://p.example.com/3",
        }
        # user_id が正しく引き継がれること
        by_endpoint = {s.endpoint: s.user_id for s in all_subs}
        assert by_endpoint["https://p.example.com/1"] == user1.id
        assert by_endpoint["https://p.example.com/2"] == user2.id

    def test_get_for_user_returns_only_that_user(
        self, db_session: Session, session_factory
    ) -> None:
        user1 = _make_user(db_session, 409)
        user2 = _make_user(db_session, 410)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/u1a", p256dh="k", auth="a", user_id=user1.id
            )
        )
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/u1b", p256dh="k", auth="a", user_id=user1.id
            )
        )
        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/u2a", p256dh="k", auth="a", user_id=user2.id
            )
        )

        result = store.get_for_user(user1.id)
        assert {s.endpoint for s in result} == {
            "https://p.example.com/u1a",
            "https://p.example.com/u1b",
        }

    def test_get_for_user_unknown_user_returns_empty(
        self, db_session: Session, session_factory
    ) -> None:
        store = DatabaseSubscriptionStore(session_factory)
        assert store.get_for_user(999999) == []

    def test_count_zero_one_multiple(self, db_session: Session, session_factory) -> None:
        user = _make_user(db_session, 411)
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)
        assert store.count() == 0

        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/c1", p256dh="k", auth="a", user_id=user.id
            )
        )
        assert store.count() == 1

        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/c2", p256dh="k", auth="a", user_id=user.id
            )
        )
        assert store.count() == 2


class TestCorruptSettingsJsonIsIrrelevant:
    """通知設定 JSON が壊れていても購読の保存は成功すること。

    2026-08-05: 以前は購読が同じ JSON セルに入っていたため、壊れた設定が
    購読の読み書きを巻き込んでいた。テーブル分離後は完全に独立なので、
    壊れた設定は購読に一切影響しない (壊れた設定の扱いは
    push_allowed_for_user 側の責務で、そちらでテストしている)。
    """

    def test_add_succeeds_even_with_corrupt_settings_json(
        self, db_session: Session, session_factory
    ) -> None:
        user = _make_user(db_session, 412, notification_settings_json="{not valid json")
        db_session.commit()
        store = DatabaseSubscriptionStore(session_factory)

        store.add(
            WebPushSubscription(
                endpoint="https://p.example.com/fallback", p256dh="k", auth="a", user_id=user.id
            )
        )

        assert len(store.get_for_user(user.id)) == 1
        db_session.refresh(user)
        assert user.notification_settings_json == "{not valid json", "設定側は触らない"
