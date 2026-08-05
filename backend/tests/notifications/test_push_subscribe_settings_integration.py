# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/notifications/test_push_subscribe_settings_integration.py
"""購読保存と通知設定が同じ列を共有していることの結合テスト (2026-08-05)。

push_subscriptions と push_enabled / preferences は **同一の
users.notification_settings_json (TEXT)** に同居している。書き手が2系統
(/push/subscribe = DatabaseSubscriptionStore と PUT /settings = router) あるため、
片方が他方を踏むと「購読はあるが設定が消えた」「設定はあるが購読が消えた」という
到達経路の静かな喪失が起きる。

本ファイルは実DB (sqlite) を使い、フロントエンドが実際に行う順序
  1. POST /push/subscribe    (購読を保存)
  2. PUT  /settings          (push_enabled=true を保存)
  3. 配信判定                 (push_allowed_for_user + get_for_user)
が最後まで繋がることを検証する。単体テストが個々に通っていても、
この結合部分が切れていれば通知は届かない。
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-push-settings-integration")

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.notifications.push import (  # noqa: E402
    DatabaseSubscriptionStore,
    WebPushSubscription,
    push_allowed_for_user,
)
from app.notifications.router import (  # noqa: E402
    NotificationSettingsModel,
    _do_update_notification_settings,
)

_ENDPOINT = "https://fcm.googleapis.com/fcm/send/integration-device"


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


def _make_user(db: Session, uid: int) -> User:
    user = User(
        id=uid,
        email=f"pushint{uid}@test.com",
        username=f"pushint{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address="0x" + f"{uid:040x}",
    )
    db.add(user)
    db.commit()
    return user


class TestSubscribeThenEnableSequence:
    """フロントエンドの実際の順序 (購読 → 設定ON) が壊れていないこと。"""

    def test_subscribe_then_settings_put_keeps_both(self, _db_env) -> None:
        """購読保存 → 設定PUT の後、購読と push_enabled が両立すること。"""
        db, factory = _db_env
        user = _make_user(db, 1)
        store = DatabaseSubscriptionStore(factory)

        # 1. 購読を保存 (POST /push/subscribe 相当)
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="pk", auth="ak", user_id=user.id))

        # 2. 設定を保存 (PUT /settings 相当。push_enabled=true)
        db.refresh(user)
        _do_update_notification_settings(
            NotificationSettingsModel(line_enabled=True, push_enabled=True), user, db
        )

        # 3. 配信判定が通り、購読が引ける
        db.refresh(user)
        assert push_allowed_for_user(user.notification_settings_json, "ai_proposal") is True
        assert [s.endpoint for s in store.get_for_user(user.id)] == [_ENDPOINT]

    def test_settings_put_first_then_subscribe_keeps_both(self, _db_env) -> None:
        """逆順 (設定ON → 購読保存) でも両立すること。

        store.add は raw JSON の push_subscriptions キーのみを差し替える契約なので、
        既存の push_enabled を落としてはいけない。
        """
        db, factory = _db_env
        user = _make_user(db, 2)
        store = DatabaseSubscriptionStore(factory)

        _do_update_notification_settings(
            NotificationSettingsModel(line_enabled=False, push_enabled=True), user, db
        )
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="pk", auth="ak", user_id=user.id))

        db.refresh(user)
        raw = json.loads(user.notification_settings_json)
        assert raw["push_enabled"] is True, "購読保存が push_enabled を消してはいけない"
        assert raw["line_enabled"] is False, "他チャネル設定も保持されること"
        assert len(raw["push_subscriptions"]) == 1

    def test_toggle_off_then_on_does_not_duplicate_or_lose(self, _db_env) -> None:
        """I-1 (短時間の往復): OFF→ON を繰り返しても購読が重複/消失しないこと。"""
        db, factory = _db_env
        user = _make_user(db, 3)
        store = DatabaseSubscriptionStore(factory)

        for _ in range(3):
            # ON: 購読 + 設定ON
            store.add(
                WebPushSubscription(endpoint=_ENDPOINT, p256dh="pk", auth="ak", user_id=user.id)
            )
            db.refresh(user)
            _do_update_notification_settings(NotificationSettingsModel(push_enabled=True), user, db)
            # OFF: 購読解除 + 設定OFF
            store.remove(_ENDPOINT)
            db.refresh(user)
            _do_update_notification_settings(
                NotificationSettingsModel(push_enabled=False), user, db
            )

        db.refresh(user)
        assert store.get_for_user(user.id) == []
        assert push_allowed_for_user(user.notification_settings_json, "ai_proposal") is False

        # 最後にもう一度ONにすると、ちゃんと1件だけ復活すること
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="pk", auth="ak", user_id=user.id))
        db.refresh(user)
        _do_update_notification_settings(NotificationSettingsModel(push_enabled=True), user, db)
        db.refresh(user)
        assert len(store.get_for_user(user.id)) == 1
        assert push_allowed_for_user(user.notification_settings_json, "ai_proposal") is True

    def test_settings_put_does_not_resurrect_removed_subscription(self, _db_env) -> None:
        """解除後の設定PUTで購読が復活しないこと (PUT は購読を「引き継ぐ」実装のため)。"""
        db, factory = _db_env
        user = _make_user(db, 4)
        store = DatabaseSubscriptionStore(factory)

        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="pk", auth="ak", user_id=user.id))
        store.remove(_ENDPOINT)

        db.refresh(user)
        _do_update_notification_settings(NotificationSettingsModel(push_enabled=True), user, db)

        db.refresh(user)
        assert store.get_for_user(user.id) == [], "解除済みの購読が復活してはいけない"

    def test_two_devices_survive_settings_put(self, _db_env) -> None:
        """I-3: 2端末購読済みの状態で設定PUTしても両方残ること。"""
        db, factory = _db_env
        user = _make_user(db, 5)
        store = DatabaseSubscriptionStore(factory)

        store.add(
            WebPushSubscription(endpoint=_ENDPOINT + "-iphone", p256dh="p", auth="a", user_id=5)
        )
        store.add(WebPushSubscription(endpoint=_ENDPOINT + "-pc", p256dh="p", auth="a", user_id=5))

        db.refresh(user)
        _do_update_notification_settings(NotificationSettingsModel(push_enabled=True), user, db)

        db.refresh(user)
        assert len(store.get_for_user(5)) == 2


class TestPreferenceGateEndToEnd:
    """preferences.ai_proposal を OFF にすると配信判定が落ちること (B-N4)。"""

    def test_ai_proposal_off_blocks_delivery_but_keeps_subscription(self, _db_env) -> None:
        """通知種別OFFでも購読自体は保持される (再ONで即復活できる)。"""
        db, factory = _db_env
        user = _make_user(db, 6)
        store = DatabaseSubscriptionStore(factory)
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p", auth="a", user_id=6))

        db.refresh(user)
        body = NotificationSettingsModel(push_enabled=True)
        body.preferences.ai_proposal = False
        _do_update_notification_settings(body, user, db)

        db.refresh(user)
        assert push_allowed_for_user(user.notification_settings_json, "ai_proposal") is False
        assert len(store.get_for_user(6)) == 1, "設定OFFで購読を消してはいけない"

    def test_emergency_stop_notification_cannot_be_disabled(self, _db_env) -> None:
        """CLAUDE.md Security Rule #6: 緊急停止通知は無効化不可 (強制 True)。"""
        db, _factory = _db_env
        user = _make_user(db, 7)

        body = NotificationSettingsModel.model_validate(
            {"push_enabled": True, "preferences": {"emergency_stop": False}}
        )
        _do_update_notification_settings(body, user, db)

        db.refresh(user)
        raw = json.loads(user.notification_settings_json)
        assert raw["preferences"]["emergency_stop"] is True
        assert push_allowed_for_user(user.notification_settings_json, "emergency_stop") is True


class TestCrossUserEndpointMigration:
    """I-12 / I-5: 同一端末で別アカウントにログインした場合。"""

    def test_endpoint_moves_to_new_user_and_leaves_old(self, _db_env) -> None:
        """同一 endpoint を別ユーザーが登録したら、旧ユーザー側から消えること。

        消えないと、退会/ログアウトした前ユーザー宛の通知が同じ端末に届き続ける
        (別人の資産情報が表示される事故になりうる)。
        """
        db, factory = _db_env
        old = _make_user(db, 10)
        new = _make_user(db, 11)
        store = DatabaseSubscriptionStore(factory)

        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p", auth="a", user_id=old.id))
        assert len(store.get_for_user(old.id)) == 1

        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p2", auth="a2", user_id=new.id))

        assert store.get_for_user(old.id) == [], "旧ユーザーから除去されるべき"
        moved = store.get_for_user(new.id)
        assert [s.endpoint for s in moved] == [_ENDPOINT]
        assert moved[0].p256dh == "p2", "新しい鍵で上書きされること"

    def test_old_user_other_settings_survive_migration(self, _db_env) -> None:
        """endpoint 移動時に旧ユーザーの他の設定を壊さないこと。"""
        db, factory = _db_env
        old = _make_user(db, 12)
        new = _make_user(db, 13)
        store = DatabaseSubscriptionStore(factory)

        _do_update_notification_settings(
            NotificationSettingsModel(line_enabled=False, push_enabled=True), old, db
        )
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p", auth="a", user_id=old.id))
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p2", auth="a2", user_id=new.id))

        db.refresh(old)
        raw = json.loads(old.notification_settings_json)
        assert raw["line_enabled"] is False
        assert raw["push_enabled"] is True
        assert raw["push_subscriptions"] == []


class TestSchedulerGateUsesRealDb:
    """配信ゲートが実DBのユーザー設定を見ていること (モックすり抜け防止)。"""

    def test_delivery_skipped_for_push_disabled_user(self, _db_env) -> None:
        from decimal import Decimal
        from unittest.mock import patch

        from app.automation.ai_judgment_scheduler import _deliver_ai_proposal_push
        from app.notifications.templates import ai_proposal_notification

        db, factory = _db_env
        user = _make_user(db, 20)
        store = DatabaseSubscriptionStore(factory)
        store.add(WebPushSubscription(endpoint=_ENDPOINT, p256dh="p", auth="a", user_id=20))
        # push_enabled を明示的に false で保存
        db.refresh(user)
        _do_update_notification_settings(NotificationSettingsModel(push_enabled=False), user, db)

        mock_sender = MagicMock()
        with (
            patch("app.notifications.push.get_vapid_config", return_value=MagicMock()),
            patch("app.notifications.push.WebPushSender", return_value=mock_sender),
        ):
            _deliver_ai_proposal_push(
                db, 20, ai_proposal_notification("SUPPLY", "USDC", Decimal("100"), 80)
            )

        mock_sender.send_to_user.assert_not_called()
