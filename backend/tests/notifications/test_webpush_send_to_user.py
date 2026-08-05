# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/notifications/test_webpush_send_to_user.py
"""WebPushSender.send_to_user の単体テスト（2026-08-04 PR5）。

send_to_all (全購読者へブロードキャスト、/push/test 専用) とは別に、AI提案通知等の
per-user 配信で使う send_to_user が「対象ユーザーの購読にのみ」送信することを検証する。
pywebpush の実HTTP送信は send_to_subscription をモックして切り離す。
"""

from __future__ import annotations

from unittest.mock import patch

from app.notifications.push import (
    DeliveryResult,
    InMemorySubscriptionStore,
    VAPIDConfig,
    WebPushSender,
    WebPushSubscription,
)


def _make_config() -> VAPIDConfig:
    return VAPIDConfig(public_key="pub", private_key="priv", mailto="ops@example.com")


def _make_store() -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    store.add(
        WebPushSubscription(endpoint="https://p.example.com/u1a", p256dh="k", auth="a", user_id=1)
    )
    store.add(
        WebPushSubscription(endpoint="https://p.example.com/u1b", p256dh="k", auth="a", user_id=1)
    )
    store.add(
        WebPushSubscription(endpoint="https://p.example.com/u2a", p256dh="k", auth="a", user_id=2)
    )
    return store


class TestSendToUser:
    """send_to_subscription をモックし、pywebpush の実インストール有無に依存しない。

    _PYWEBPUSH_AVAILABLE ガード自体は import-time フラグで実パッケージ有無を反映するため、
    ここでは True 固定パッチして send_to_user 内のルーティングロジックのみ検証する。
    """

    def test_sends_only_to_target_user_subscriptions(self) -> None:
        """user_id=1 への配信は user_id=1 の2件のみ send_to_subscription を呼ぶ。"""
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.SUCCESS
            ) as mock_send,
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is True
        called_endpoints = {c.args[0].endpoint for c in mock_send.call_args_list}
        assert called_endpoints == {
            "https://p.example.com/u1a",
            "https://p.example.com/u1b",
        }

    def test_other_user_subscriptions_are_not_touched(self) -> None:
        """user_id=2 の購読には送信されないこと。"""
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.SUCCESS
            ) as mock_send,
        ):
            sender.send_to_user(1, {"title": "t", "body": "b"})

        called_endpoints = {c.args[0].endpoint for c in mock_send.call_args_list}
        assert "https://p.example.com/u2a" not in called_endpoints

    def test_returns_false_when_no_subscription_for_user(self) -> None:
        """購読が無いユーザーは False。"""
        store = InMemorySubscriptionStore()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.SUCCESS
            ) as mock_send,
        ):
            result = sender.send_to_user(999, {"title": "t", "body": "b"})

        assert result is False
        mock_send.assert_not_called()

    def test_returns_true_if_at_least_one_subscription_succeeds(self) -> None:
        """複数端末のうち1件でも成功すれば True。"""
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender,
                "send_to_subscription",
                side_effect=[DeliveryResult.FAILED_TRANSIENT, DeliveryResult.SUCCESS],
            ),
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is True

    def test_returns_false_when_all_subscriptions_fail(self) -> None:
        """全端末失敗なら False。"""
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.FAILED_TRANSIENT
            ),
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is False

    def test_gone_subscription_is_removed_from_store(self) -> None:
        """失効(410/404)した購読のみ store.remove で削除される。

        2026-08-05: 以前は「失敗した購読」を一律削除していたため、一時エラーでも
        購読が消えていた。一時エラーで消さないことの検証は
        test_push_delivery_hardening.py::TestGoneVsTransientFailure が担う。
        """
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender,
                "send_to_subscription",
                side_effect=[DeliveryResult.SUCCESS, DeliveryResult.FAILED_GONE],
            ),
        ):
            sender.send_to_user(1, {"title": "t", "body": "b"})

        remaining = {s.endpoint for s in store.get_for_user(1)}
        assert len(remaining) == 1

    def test_pywebpush_unavailable_returns_false_without_calling_store(self) -> None:
        """pywebpush 未インストール環境では静かに False を返す (既存 send_to_all と同じ fail-open)。"""
        store = _make_store()
        sender = WebPushSender(_make_config(), store)

        with patch("app.notifications.push._PYWEBPUSH_AVAILABLE", False):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is False
