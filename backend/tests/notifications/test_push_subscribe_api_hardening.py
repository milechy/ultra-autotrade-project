# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/notifications/test_push_subscribe_api_hardening.py
"""/push/subscribe, /push/unsubscribe の入力検証・認可のテスト (2026-08-05)。

既存テストは 200 が返ることを確認していたが、以下が未検証だった:
- 他ユーザーの endpoint を指定して購読を削除できてしまわないか (認可スコープ)
- 鍵 (p256dh / auth) が空でも保存されてしまわないか (trust boundary の検証)
- 購読数レスポンスが他ユーザー分を含めて漏らしていないか

いずれも「境界での検証」と「認可」に該当し、CLAUDE.md の
「新規エンドポイントには RBAC を必ず実装」「認証状態で表示が変わる操作系はガード」
の対象。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.notifications.push import InMemorySubscriptionStore, WebPushSubscription
from app.notifications.router import api_router, get_subscription_store, router

_ENDPOINT_A = "https://fcm.googleapis.com/fcm/send/user-a-device"
_ENDPOINT_B = "https://fcm.googleapis.com/fcm/send/user-b-device"


def _make_client(store: InMemorySubscriptionStore, user_id: int) -> TestClient:
    """指定ユーザーとして認証済みのクライアントを作る。"""
    from app.auth.dependencies import require_active_user

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)

    user = MagicMock()
    user.id = user_id
    app.dependency_overrides[require_active_user] = lambda: user
    app.dependency_overrides[get_subscription_store] = lambda: store
    return TestClient(app)


def _store_with_two_users() -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    store.add(WebPushSubscription(endpoint=_ENDPOINT_A, p256dh="k", auth="a", user_id=1))
    store.add(WebPushSubscription(endpoint=_ENDPOINT_B, p256dh="k", auth="a", user_id=2))
    return store


# ---------------------------------------------------------------------------
# 認可: 他ユーザーの購読を消せないこと
# ---------------------------------------------------------------------------


class TestUnsubscribeAuthorizationScope:
    """endpoint を知っていても他人の購読は削除できないこと。

    endpoint は推測困難な長い URL だが、認可はスコープで担保すべきで
    「値が推測しにくい」ことに依存させない (URLはログ・スクショ経由で漏れうる)。
    """

    def test_cannot_remove_other_users_subscription(self) -> None:
        store = _store_with_two_users()
        client = _make_client(store, user_id=1)  # user 1 として user 2 の endpoint を狙う

        response = client.request(
            "DELETE", "/notifications/push/unsubscribe", params={"endpoint": _ENDPOINT_B}
        )

        assert response.status_code == 200, "冪等な no-op として扱う (存在露出を避ける)"
        remaining = {s.endpoint for s in store.get_for_user(2)}
        assert remaining == {_ENDPOINT_B}, "他ユーザーの購読が削除されてはいけない"

    def test_can_remove_own_subscription(self) -> None:
        store = _store_with_two_users()
        client = _make_client(store, user_id=1)

        response = client.request(
            "DELETE", "/notifications/push/unsubscribe", params={"endpoint": _ENDPOINT_A}
        )

        assert response.status_code == 200
        assert store.get_for_user(1) == []

    def test_unsubscribe_is_idempotent(self) -> None:
        """I-7 / I-11 (連打・リトライ): 2回目も 200 で落ちないこと。"""
        store = _store_with_two_users()
        client = _make_client(store, user_id=1)

        first = client.request(
            "DELETE", "/notifications/push/unsubscribe", params={"endpoint": _ENDPOINT_A}
        )
        second = client.request(
            "DELETE", "/notifications/push/unsubscribe", params={"endpoint": _ENDPOINT_A}
        )

        assert first.status_code == 200
        assert second.status_code == 200

    def test_count_does_not_leak_other_users(self) -> None:
        """レスポンスの count は自分の購読数のみ (全体数を漏らさない)。"""
        store = _store_with_two_users()
        client = _make_client(store, user_id=1)

        response = client.request(
            "DELETE", "/notifications/push/unsubscribe", params={"endpoint": _ENDPOINT_A}
        )

        assert response.json()["count"] == 0, "user1 の購読数のみ。全体(1件残)を返してはいけない"


# ---------------------------------------------------------------------------
# 入力検証: 鍵が空の購読を受け付けないこと
# ---------------------------------------------------------------------------


class TestSubscribeInputValidation:
    """空の鍵を保存すると、送信時に必ず失敗する死んだ購読が残る。

    「保存はできるが絶対に届かない」状態は到達経路の可視性を損なうため、
    境界で弾く (CLAUDE.md: 入力検証は trust boundary で行う)。
    """

    @pytest.mark.parametrize(
        "body",
        [
            {"endpoint": _ENDPOINT_A},  # keys 完全欠落
            {"endpoint": _ENDPOINT_A, "p256dh": "", "auth": ""},  # 空文字
            {"endpoint": _ENDPOINT_A, "p256dh": "k", "auth": ""},  # auth のみ空
            {"endpoint": _ENDPOINT_A, "p256dh": "", "auth": "a"},  # p256dh のみ空
            {"endpoint": _ENDPOINT_A, "keys": {"p256dh": "", "auth": ""}},  # ネスト形式で空
        ],
    )
    def test_missing_or_empty_keys_rejected(self, body: dict[str, Any]) -> None:
        store = InMemorySubscriptionStore()
        client = _make_client(store, user_id=1)

        response = client.post("/notifications/push/subscribe", json=body)

        assert response.status_code == 422, f"空鍵は 422 で弾くべき: {body}"
        assert store.count() == 0, "検証失敗時に保存してはいけない"

    def test_empty_endpoint_rejected(self) -> None:
        store = InMemorySubscriptionStore()
        client = _make_client(store, user_id=1)

        response = client.post(
            "/notifications/push/subscribe",
            json={"endpoint": "", "p256dh": "k", "auth": "a"},
        )

        assert response.status_code == 422
        assert store.count() == 0

    def test_valid_browser_format_accepted(self) -> None:
        """正常系: ブラウザ標準形式 (keys ネスト) が通り、user_id が紐付くこと。"""
        store = InMemorySubscriptionStore()
        client = _make_client(store, user_id=42)

        response = client.post(
            "/notifications/push/subscribe",
            json={"endpoint": _ENDPOINT_A, "keys": {"p256dh": "pk", "auth": "ak"}},
        )

        assert response.status_code == 200
        subs = store.get_for_user(42)
        assert [s.endpoint for s in subs] == [_ENDPOINT_A]
        assert subs[0].p256dh == "pk"
        assert subs[0].auth == "ak"

    def test_valid_flat_format_accepted(self) -> None:
        """正常系: フラット形式も従来どおり通ること (後方互換)。"""
        store = InMemorySubscriptionStore()
        client = _make_client(store, user_id=42)

        response = client.post(
            "/notifications/push/subscribe",
            json={"endpoint": _ENDPOINT_A, "p256dh": "pk", "auth": "ak"},
        )

        assert response.status_code == 200
        assert store.count() == 1

    def test_resubscribe_same_endpoint_does_not_duplicate(self) -> None:
        """I-1 / I-5 (往復・再追加): 同一 endpoint の再登録で重複しないこと。"""
        store = InMemorySubscriptionStore()
        client = _make_client(store, user_id=42)
        body = {"endpoint": _ENDPOINT_A, "p256dh": "pk", "auth": "ak"}

        client.post("/notifications/push/subscribe", json=body)
        client.post("/notifications/push/subscribe", json=body)

        assert len(store.get_for_user(42)) == 1

    def test_subscribe_count_is_per_user(self) -> None:
        """レスポンスの count は自分の購読数のみ。"""
        store = _store_with_two_users()
        client = _make_client(store, user_id=1)

        response = client.post(
            "/notifications/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/new",
                "p256dh": "k",
                "auth": "a",
            },
        )

        assert response.json()["count"] == 2, "user1 の2件のみ (全体3件を返してはいけない)"
