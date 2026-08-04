# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_notifications.py
"""通知基盤 Phase 1 のテスト。"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.notifications.line_messaging import LINEFlexMessageSender, build_alert_flex_bubble
from app.notifications.push import InMemorySubscriptionStore, WebPushSubscription
from app.notifications.templates import (
    NotificationPayload,
    ai_proposal_notification,
    approval_timeout_notification,
    auto_safety_action_notification,
    emergency_stop_notification,
    hf_danger_alert,
    trade_executed_notification,
    trade_failed_notification,
)

# ---------------------------------------------------------------------------
# テスト用 FastAPI アプリ（DB なし）
# ---------------------------------------------------------------------------


def _create_test_app():
    """テスト用の最小 FastAPI アプリを作成する。"""
    from fastapi import FastAPI

    from app.notifications.router import router as notification_router

    app = FastAPI()
    app.include_router(notification_router)
    return app


def _create_web_push_test_app():
    """TestWebPushRouter 用アプリ。require_active_user と subscription store を
    DB 非依存にオーバーライドする (2026-08-04 PR3: subscribe/unsubscribe が認証必須化 +
    ストアが DatabaseSubscriptionStore になったため、素の _create_test_app のままでは
    401 になる / 実 DB へ接続しようとしてしまう)。"""
    from unittest.mock import MagicMock

    from fastapi import FastAPI

    from app.auth.dependencies import require_active_user
    from app.notifications.push import InMemorySubscriptionStore
    from app.notifications.router import get_subscription_store
    from app.notifications.router import router as notification_router

    app = FastAPI()
    app.include_router(notification_router)

    test_user = MagicMock()
    test_user.id = 999
    shared_store = InMemorySubscriptionStore()
    app.dependency_overrides[require_active_user] = lambda: test_user
    app.dependency_overrides[get_subscription_store] = lambda: shared_store
    return app


# ---------------------------------------------------------------------------
# 1. テンプレートテスト
# ---------------------------------------------------------------------------


class TestNotificationTemplates:
    """7種の通知テンプレートのテスト。"""

    def test_hf_danger_alert_returns_payload(self):
        payload = hf_danger_alert(Decimal("1.2"))
        assert isinstance(payload, NotificationPayload)

    def test_hf_danger_alert_severity_emergency(self):
        payload = hf_danger_alert(Decimal("1.2"))
        assert payload.severity == "emergency"

    def test_hf_danger_alert_body_contains_hf(self):
        payload = hf_danger_alert(Decimal("1.25"))
        assert "1.250" in payload.body

    def test_emergency_stop_notification_returns_payload(self):
        payload = emergency_stop_notification("テスト理由")
        assert isinstance(payload, NotificationPayload)
        assert payload.severity == "emergency"

    def test_emergency_stop_notification_body_contains_reason(self):
        payload = emergency_stop_notification("HF低下")
        assert "HF低下" in payload.body

    def test_auto_safety_action_notification_returns_payload(self):
        payload = auto_safety_action_notification("SUPPLY", "USDC", Decimal("1000"), Decimal("3.5"))
        assert isinstance(payload, NotificationPayload)
        assert payload.severity == "alert"

    def test_auto_safety_action_withdraw(self):
        payload = auto_safety_action_notification("WITHDRAW", "ETH", Decimal("0.5"), Decimal("2.1"))
        assert "引き出し" in payload.body

    def test_ai_proposal_notification_returns_payload(self):
        payload = ai_proposal_notification("SUPPLY", "USDC", Decimal("1000"), 85)
        assert isinstance(payload, NotificationPayload)

    def test_ai_proposal_notification_severity_warning(self):
        payload = ai_proposal_notification("SUPPLY", "USDC", Decimal("1000"), 85)
        assert payload.severity == "warning"

    def test_trade_executed_notification_returns_payload(self):
        payload = trade_executed_notification("BUY", "ETH", Decimal("0.1"), "0xabcdef1234567890")
        assert isinstance(payload, NotificationPayload)
        assert payload.severity == "info"

    def test_trade_executed_notification_tx_hash_truncated(self):
        payload = trade_executed_notification("BUY", "ETH", Decimal("0.1"), "0xabcdef1234567890")
        assert "0xabcdef12" in payload.body

    def test_trade_failed_notification_returns_payload(self):
        payload = trade_failed_notification("SELL", "BTC", Decimal("0.01"), "Connection timeout")
        assert isinstance(payload, NotificationPayload)
        assert payload.severity == "alert"

    def test_approval_timeout_notification_returns_payload(self):
        payload = approval_timeout_notification("SUPPLY", "USDC")
        assert isinstance(payload, NotificationPayload)
        assert payload.severity == "info"

    def test_approval_timeout_custom_minutes(self):
        payload = approval_timeout_notification("WITHDRAW", "ETH", timeout_minutes=30)
        assert "30" in payload.body

    def test_web_push_payload_has_required_fields(self):
        payload = hf_danger_alert(Decimal("1.1"))
        wp = payload.web_push_payload
        assert "title" in wp
        assert "body" in wp
        assert "icon" in wp
        assert "tag" in wp

    def test_web_push_payload_emergency_requires_interaction(self):
        payload = hf_danger_alert(Decimal("1.1"))
        assert payload.web_push_payload["requireInteraction"] is True

    def test_web_push_payload_info_no_require_interaction(self):
        payload = approval_timeout_notification("SUPPLY", "USDC")
        assert payload.web_push_payload["requireInteraction"] is False

    def test_line_flex_color_emergency(self):
        payload = hf_danger_alert(Decimal("1.1"))
        assert payload.line_flex_color == "#FF0000"

    def test_line_flex_color_alert(self):
        payload = auto_safety_action_notification("SUPPLY", "USDC", Decimal("100"), Decimal("2.0"))
        assert payload.line_flex_color == "#FF6B00"

    def test_line_flex_color_warning(self):
        payload = ai_proposal_notification("SUPPLY", "USDC", Decimal("100"), 70)
        assert payload.line_flex_color == "#FFA500"

    def test_line_flex_color_info(self):
        payload = approval_timeout_notification("SUPPLY", "USDC")
        assert payload.line_flex_color == "#00B900"

    def test_notification_message_logged(self):
        from app.notifications.schemas import NotificationMessage

        payload = hf_danger_alert(Decimal("1.2"))
        assert isinstance(payload.notification_message, NotificationMessage)

    def test_all_templates_return_payload(self):
        """全7テンプレートが NotificationPayload を返すことを確認。"""
        payloads = [
            hf_danger_alert(Decimal("1.2")),
            emergency_stop_notification("test"),
            auto_safety_action_notification("SUPPLY", "USDC", Decimal("100"), Decimal("3.0")),
            ai_proposal_notification("SUPPLY", "USDC", Decimal("100"), 80),
            trade_executed_notification("BUY", "ETH", Decimal("1"), "0x" + "a" * 40),
            trade_failed_notification("SELL", "BTC", Decimal("0.1"), "error"),
            approval_timeout_notification("SUPPLY", "USDC"),
        ]
        assert len(payloads) == 7
        for p in payloads:
            assert isinstance(p, NotificationPayload)


# ---------------------------------------------------------------------------
# 2. InMemorySubscriptionStore テスト
# ---------------------------------------------------------------------------


class TestInMemorySubscriptionStore:
    """InMemorySubscriptionStore の動作確認。"""

    def _make_sub(self, endpoint: str = "https://example.com/push/1") -> WebPushSubscription:
        return WebPushSubscription(endpoint=endpoint, p256dh="dummykey", auth="dummyauth")

    def test_initial_count_is_zero(self):
        store = InMemorySubscriptionStore()
        assert store.count() == 0

    def test_add_subscription(self):
        store = InMemorySubscriptionStore()
        store.add(self._make_sub())
        assert store.count() == 1

    def test_add_duplicate_endpoint_overwrites(self):
        store = InMemorySubscriptionStore()
        sub1 = WebPushSubscription(endpoint="https://example.com/push/1", p256dh="k1", auth="a1")
        sub2 = WebPushSubscription(endpoint="https://example.com/push/1", p256dh="k2", auth="a2")
        store.add(sub1)
        store.add(sub2)
        assert store.count() == 1
        # 最後のものが保持される
        assert store.get_all()[0].p256dh == "k2"

    def test_remove_subscription(self):
        store = InMemorySubscriptionStore()
        sub = self._make_sub("https://example.com/push/1")
        store.add(sub)
        store.remove("https://example.com/push/1")
        assert store.count() == 0

    def test_remove_nonexistent_endpoint_is_noop(self):
        store = InMemorySubscriptionStore()
        store.remove("https://example.com/push/nonexistent")
        assert store.count() == 0

    def test_get_all_returns_all(self):
        store = InMemorySubscriptionStore()
        store.add(self._make_sub("https://example.com/push/1"))
        store.add(self._make_sub("https://example.com/push/2"))
        result = store.get_all()
        assert len(result) == 2

    def test_get_all_returns_copy(self):
        """get_all() の結果を変更してもストアに影響しないこと。"""
        store = InMemorySubscriptionStore()
        store.add(self._make_sub())
        result = store.get_all()
        result.clear()
        assert store.count() == 1


# ---------------------------------------------------------------------------
# 3. Web Push Router テスト
# ---------------------------------------------------------------------------


class TestWebPushRouter:
    """Push Subscription 管理 API のテスト（TestClient）。"""

    @pytest.fixture
    def client(self):
        app = _create_web_push_test_app()
        return TestClient(app, raise_server_exceptions=True)

    def test_vapid_key_returns_null_when_not_configured(self, client: TestClient):
        """VAPID 未設定時は publicKey: null を返す。"""
        response = client.get("/notifications/push/vapid-key")
        assert response.status_code == 200
        data = response.json()
        assert "publicKey" in data
        assert data["publicKey"] is None

    def test_subscribe_returns_200(self, client: TestClient):
        """POST /subscribe が 200 を返すこと。"""
        response = client.post(
            "/notifications/push/subscribe",
            json={
                "endpoint": "https://example.com/push/test",
                "p256dh": "dummykey",
                "auth": "dummyauth",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "subscribed"

    def test_unsubscribe_returns_200(self, client: TestClient):
        """DELETE /unsubscribe が 200 を返すこと。"""
        response = client.delete(
            "/notifications/push/unsubscribe",
            params={"endpoint": "https://example.com/push/test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unsubscribed"

    def test_subscribe_and_unsubscribe_lifecycle(self, client: TestClient):
        """subscribe → unsubscribe のライフサイクルテスト。"""
        endpoint = "https://example.com/push/lifecycle"
        # subscribe
        resp = client.post(
            "/notifications/push/subscribe",
            json={"endpoint": endpoint, "p256dh": "key", "auth": "auth"},
        )
        assert resp.status_code == 200

        # unsubscribe
        resp = client.delete(
            "/notifications/push/unsubscribe",
            params={"endpoint": endpoint},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. LINE Flex Message テスト
# ---------------------------------------------------------------------------


class TestLINEFlexMessage:
    """LINE Flex Message 構造のテスト。"""

    def test_build_alert_flex_bubble_structure(self):
        """build_alert_flex_bubble() が正しい構造の dict を返すこと。"""
        bubble = build_alert_flex_bubble("テストタイトル", "テスト本文", "emergency", "#FF0000")
        assert bubble["type"] == "flex"
        assert bubble["altText"] == "テストタイトル"
        contents = bubble["contents"]
        assert contents["type"] == "bubble"
        assert "header" in contents
        assert "body" in contents

    def test_flex_bubble_header_color_emergency(self):
        """emergency の場合ヘッダーが赤色になること。"""
        bubble = build_alert_flex_bubble("title", "body", "emergency", "#FF0000")
        assert bubble["contents"]["header"]["backgroundColor"] == "#FF0000"

    def test_flex_bubble_header_color_alert(self):
        bubble = build_alert_flex_bubble("title", "body", "alert", "#FF6B00")
        assert bubble["contents"]["header"]["backgroundColor"] == "#FF6B00"

    def test_flex_bubble_header_color_warning(self):
        bubble = build_alert_flex_bubble("title", "body", "warning", "#FFA500")
        assert bubble["contents"]["header"]["backgroundColor"] == "#FFA500"

    def test_flex_bubble_header_color_info(self):
        bubble = build_alert_flex_bubble("title", "body", "info", "#00B900")
        assert bubble["contents"]["header"]["backgroundColor"] == "#00B900"

    def test_flex_bubble_header_contains_title(self):
        bubble = build_alert_flex_bubble("My Title", "body", "info", "#00B900")
        header_texts = [
            item["text"]
            for item in bubble["contents"]["header"]["contents"]
            if item.get("type") == "text"
        ]
        assert "My Title" in header_texts

    def test_flex_bubble_body_contains_body_text(self):
        bubble = build_alert_flex_bubble("title", "My Body Text", "info", "#00B900")
        body_texts = [
            item["text"]
            for item in bubble["contents"]["body"]["contents"]
            if item.get("type") == "text"
        ]
        assert "My Body Text" in body_texts

    def test_line_flex_sender_instantiation(self):
        """LINEFlexMessageSender が正常にインスタンス化できること。"""
        sender = LINEFlexMessageSender(
            channel_access_token="dummy_token",
            user_id="dummy_user",
        )
        assert sender is not None
