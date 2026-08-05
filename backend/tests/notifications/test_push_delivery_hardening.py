# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/notifications/test_push_delivery_hardening.py
"""Web Push 到達経路の「壊れやすいポイント」を突くテスト (2026-08-05)。

既存テスト (test_push_subscription_store.py / test_webpush_send_to_user.py /
test_notification_settings_api.py) は正常系とストア機構を押さえているが、
以下の壊れやすい箇所が未検証だった。本ファイルはそこだけを狙う。

対象 (docs/internal/2026-08-04_execution_pipeline_requirements.md の受け入れ条件):
- B-N4  : 通知設定で提案通知を無効にしたら配信されない
- B-E1  : 失効した配信先 (410 Gone) は除去される
- B-E2  : 配信サービスのエラーは「未到達」記録に留め、購読を消さない
- B-B1  : 購読数 0件 / 1件 / 複数端末
- I-3   : iPhone + PC の2台購読 → 両方へ配信、片方失敗でも他方は生きる
- I-4   : OS設定で後から拒否 → 失効検知で除去、到達経路ゼロとして扱う
- I-5   : PWA 削除→再追加 → 新規購読を受け付け、旧購読は失効検知で除去
- I-14  : 通知OFFのまま承認型を使い続ける (到達経路ゼロの自己再現) の検知前提

「一時エラーで購読を消してしまう」= 25日間サイレント障害と同型の
"可観測性なき到達経路喪失" なので、本ファイルの最重要ケースとして扱う。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.notifications.push import (
    _PYWEBPUSH_AVAILABLE,
    DeliveryResult,
    InMemorySubscriptionStore,
    VAPIDConfig,
    WebPushSender,
    WebPushSubscription,
)


def _config() -> VAPIDConfig:
    return VAPIDConfig(public_key="pub", private_key="priv", mailto="ops@example.com")


def _sub(endpoint: str, user_id: int | None = 1) -> WebPushSubscription:
    return WebPushSubscription(endpoint=endpoint, p256dh="k", auth="a", user_id=user_id)


# ---------------------------------------------------------------------------
# 1. 失効(410) と 一時エラー の区別 — B-E1 / B-E2 / I-4
# ---------------------------------------------------------------------------


class TestGoneVsTransientFailure:
    """一時エラーで購読を消さないこと。消すのは 410 Gone のみ。

    ここが壊れると FCM の一時障害1回で全ユーザーの購読が消え、
    ユーザーが手動で再購読するまで永久に通知が届かない
    (= 今回の障害と同型の静かな到達経路喪失)。
    """

    def test_transient_failure_keeps_subscription(self) -> None:
        """一時エラー(タイムアウト/500等)では購読を削除しない。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p.example.com/a"))
        sender = WebPushSender(_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.FAILED_TRANSIENT
            ),
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is False, "一時エラーなので未到達"
        assert len(store.get_for_user(1)) == 1, "一時エラーで購読が消えてはいけない"

    def test_gone_failure_removes_subscription(self) -> None:
        """410 Gone (購読失効) は削除する — I-4 / I-5 の後片付け。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p.example.com/a"))
        sender = WebPushSender(_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(sender, "send_to_subscription", return_value=DeliveryResult.FAILED_GONE),
        ):
            sender.send_to_user(1, {"title": "t", "body": "b"})

        assert store.get_for_user(1) == [], "失効した購読は除去されるべき"

    def test_unexpected_exception_keeps_subscription(self) -> None:
        """予期しない例外は「失効」と判断できないので購読を残す (fail-safe側に倒す)。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p.example.com/a"))
        sender = WebPushSender(_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(sender, "send_to_subscription", side_effect=RuntimeError("boom")),
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is False
        assert len(store.get_for_user(1)) == 1, "原因不明の失敗で購読を捨ててはいけない"

    def test_mixed_gone_and_transient_removes_only_gone(self) -> None:
        """混在時: 410 の端末だけ消え、一時エラーの端末は残る (I-3 の複数端末)。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p.example.com/iphone"))
        store.add(_sub("https://p.example.com/pc"))
        sender = WebPushSender(_config(), store)

        def _by_endpoint(sub: WebPushSubscription, *_args: Any, **_kw: Any) -> DeliveryResult:
            return (
                DeliveryResult.FAILED_GONE
                if sub.endpoint.endswith("iphone")
                else DeliveryResult.FAILED_TRANSIENT
            )

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(sender, "send_to_subscription", side_effect=_by_endpoint),
        ):
            sender.send_to_user(1, {"title": "t", "body": "b"})

        remaining = {s.endpoint for s in store.get_for_user(1)}
        assert remaining == {"https://p.example.com/pc"}

    def test_send_to_all_also_keeps_transient_failures(self) -> None:
        """send_to_all (/push/test 経路) にも同じ規律が効くこと。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p.example.com/a", user_id=1))
        store.add(_sub("https://p.example.com/b", user_id=2))
        sender = WebPushSender(_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.FAILED_TRANSIENT
            ),
        ):
            sent = sender.send_to_all({"title": "t", "body": "b"})

        assert sent == 0
        assert store.count() == 2, "一時エラーで全購読が消えてはいけない"


@pytest.mark.skipif(
    not _PYWEBPUSH_AVAILABLE,
    reason="pywebpush 未インストール環境ではライブラリ統合部分を検証できない "
    "(requirements.txt に pywebpush>=2.0.0 があるため CI / 本番イメージでは実行される)",
)
class TestDeliveryResultClassification:
    """send_to_subscription が pywebpush の応答を正しく3分類すること。"""

    @staticmethod
    def _sender() -> WebPushSender:
        return WebPushSender(_config(), InMemorySubscriptionStore())

    def test_success_is_success(self) -> None:
        with patch("app.notifications.push.webpush", return_value=None):
            result = self._sender().send_to_subscription(_sub("https://p/x"), {"a": 1}, 60)
        assert result is DeliveryResult.SUCCESS

    @pytest.mark.parametrize("status_code", [404, 410])
    def test_404_and_410_are_gone(self, status_code: int) -> None:
        """404/410 はどちらも購読消滅を意味する (RFC8030 実装差の吸収)。"""
        exc = _make_webpush_exception(status_code)
        with patch("app.notifications.push.webpush", side_effect=exc):
            result = self._sender().send_to_subscription(_sub("https://p/x"), {"a": 1}, 60)
        assert result is DeliveryResult.FAILED_GONE

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_server_errors_are_transient(self, status_code: int) -> None:
        """429/5xx は一時エラー: 購読は生きている可能性があるので消さない。"""
        exc = _make_webpush_exception(status_code)
        with patch("app.notifications.push.webpush", side_effect=exc):
            result = self._sender().send_to_subscription(_sub("https://p/x"), {"a": 1}, 60)
        assert result is DeliveryResult.FAILED_TRANSIENT

    def test_network_error_without_response_is_transient(self) -> None:
        """response を持たない例外 (DNS/接続失敗等) も一時エラー扱い。"""
        with patch("app.notifications.push.webpush", side_effect=OSError("connection refused")):
            result = self._sender().send_to_subscription(_sub("https://p/x"), {"a": 1}, 60)
        assert result is DeliveryResult.FAILED_TRANSIENT


def _make_webpush_exception(status_code: int) -> Exception:
    """status_code を持つ WebPushException 相当の例外を作る。"""
    from pywebpush import WebPushException  # noqa: PLC0415

    response = MagicMock()
    response.status_code = status_code
    exc = WebPushException("boom", response=response)
    return exc


# ---------------------------------------------------------------------------
# 2. 破損した notification_settings_json への耐性
# ---------------------------------------------------------------------------


class TestCorruptSettingsJsonRobustness:
    """dict 以外の有効JSON が入っていてもクラッシュしないこと。

    `null` / `[1,2]` / `123` / `"str"` はいずれも json.loads が成功するため
    JSONDecodeError では捕まらない。クラッシュすると呼び出し元の
    except Exception に飲まれて「静かに配信スキップ」になり、
    到達経路が黙って失われる (本プロジェクトが最も避けたい失敗形)。
    """

    @pytest.mark.parametrize("raw", ["null", "[1,2]", "123", '"str"', "{}", ""])
    def test_read_never_raises(self, raw: str) -> None:
        from app.notifications.push import DatabaseSubscriptionStore

        assert DatabaseSubscriptionStore._read_push_subscriptions(raw) == []

    @pytest.mark.parametrize("raw", ["null", "[1,2]", "123", '"str"'])
    def test_write_never_raises_and_produces_dict(self, raw: str) -> None:
        from app.notifications.push import DatabaseSubscriptionStore

        out = DatabaseSubscriptionStore._write_push_subscriptions(
            raw, [{"endpoint": "e", "p256dh": "p", "auth": "a"}]
        )
        parsed = json.loads(out)
        assert isinstance(parsed, dict)
        assert parsed["push_subscriptions"][0]["endpoint"] == "e"

    def test_write_preserves_other_keys_from_valid_dict(self) -> None:
        """正常な dict の場合は他キー (push_enabled 等) を保持すること。"""
        from app.notifications.push import DatabaseSubscriptionStore

        out = DatabaseSubscriptionStore._write_push_subscriptions(
            json.dumps({"push_enabled": True, "line_enabled": False}), []
        )
        parsed = json.loads(out)
        assert parsed["push_enabled"] is True
        assert parsed["line_enabled"] is False

    @pytest.mark.parametrize(
        "entry",
        [
            {"p256dh": "p", "auth": "a"},  # endpoint 欠落
            {"endpoint": "e", "auth": "a"},  # p256dh 欠落
            {"endpoint": "e", "p256dh": "p"},  # auth 欠落
            "not-a-dict",  # 要素が dict ですらない
            None,
        ],
    )
    def test_malformed_entry_is_skipped_not_fatal(self, entry: Any) -> None:
        """壊れた要素は飛ばし、他の正常な購読は生き残ること。"""
        from app.notifications.push import DatabaseSubscriptionStore

        good = {"endpoint": "https://p/good", "p256dh": "p", "auth": "a"}
        user = MagicMock()
        user.id = 1
        user.notification_settings_json = json.dumps({"push_subscriptions": [entry, good]})
        db = MagicMock()
        db.get.return_value = user

        store = DatabaseSubscriptionStore(lambda: db)
        result = store.get_for_user(1)

        assert [s.endpoint for s in result] == ["https://p/good"]


# ---------------------------------------------------------------------------
# 3. 通知設定 (push_enabled / preferences.ai_proposal) の尊重 — B-N4 / I-14
# ---------------------------------------------------------------------------


class TestProposalPushRespectsUserSettings:
    """通知OFFのユーザーへ配信しないこと。

    ここが壊れると「設定画面でOFFにしたのに通知が来る」= 明確な信頼毀損。
    受け入れ条件 B-N4 が直接要求している。
    """

    @staticmethod
    def _payload() -> Any:
        from app.notifications.templates import ai_proposal_notification

        return ai_proposal_notification("SUPPLY", "USDC", Decimal("100"), 80)

    @staticmethod
    def _run(settings_json: str | None) -> tuple[MagicMock, MagicMock]:
        """指定の notification_settings_json を持つユーザーへ配信を試み、(db, sender) を返す。"""
        from app.automation.ai_judgment_scheduler import _deliver_ai_proposal_push

        user = MagicMock()
        user.id = 7
        user.notification_settings_json = settings_json

        db = MagicMock()
        db.get.return_value = user

        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = True

        with (
            patch("app.notifications.push.get_vapid_config", return_value=MagicMock()),
            patch("app.notifications.push.WebPushSender", return_value=mock_sender),
            patch("app.notifications.push.DatabaseSubscriptionStore"),
            patch(
                "app.automation.ai_judgment_scheduler.SessionLocal",
                return_value=db,
            ),
        ):
            _deliver_ai_proposal_push(db, 7, TestProposalPushRespectsUserSettings._payload())
        return db, mock_sender

    def test_push_disabled_does_not_send(self) -> None:
        """push_enabled=false のユーザーには送信しない。"""
        _db, sender = self._run(json.dumps({"push_enabled": False}))
        sender.send_to_user.assert_not_called()

    def test_ai_proposal_preference_off_does_not_send(self) -> None:
        """preferences.ai_proposal=false なら AI提案通知は送らない。"""
        _db, sender = self._run(
            json.dumps({"push_enabled": True, "preferences": {"ai_proposal": False}})
        )
        sender.send_to_user.assert_not_called()

    def test_push_enabled_with_preference_on_sends(self) -> None:
        """両方ONなら送信する (正常系)。"""
        _db, sender = self._run(
            json.dumps({"push_enabled": True, "preferences": {"ai_proposal": True}})
        )
        sender.send_to_user.assert_called_once()

    def test_settings_unset_defaults_to_not_sending(self) -> None:
        """設定未保存 (NULL) は push_enabled 既定 False に従い送らない。

        NotificationSettingsModel.push_enabled のデフォルトが False であり、
        「明示的に有効化していないユーザーには送らない」が既定の約束。
        """
        _db, sender = self._run(None)
        sender.send_to_user.assert_not_called()

    def test_corrupt_settings_json_does_not_crash(self) -> None:
        """破損JSONでも例外を投げずに済むこと (fail-open、提案生成は止めない)。"""
        _db, sender = self._run("{{{not json")
        # クラッシュしないことが要件。送る/送らないはどちらでも可だが例外は不可。
        assert sender.send_to_user.call_count in (0, 1)


# ---------------------------------------------------------------------------
# 4. 複数端末 (I-3) と再購読 (I-5) — B-B1
# ---------------------------------------------------------------------------


class TestMultiDeviceAndResubscribe:
    def test_all_devices_receive(self) -> None:
        """I-3: iPhone と PC の両方へ配信されること。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p/iphone"))
        store.add(_sub("https://p/pc"))
        sender = WebPushSender(_config(), store)

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(
                sender, "send_to_subscription", return_value=DeliveryResult.SUCCESS
            ) as mock_send,
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is True
        assert {c.args[0].endpoint for c in mock_send.call_args_list} == {
            "https://p/iphone",
            "https://p/pc",
        }

    def test_one_device_gone_other_still_delivered(self) -> None:
        """I-5: 旧端末が失効しても新端末には届き、旧だけ除去される。"""
        store = InMemorySubscriptionStore()
        store.add(_sub("https://p/old-pwa"))
        store.add(_sub("https://p/new-pwa"))
        sender = WebPushSender(_config(), store)

        def _by_endpoint(sub: WebPushSubscription, *_a: Any, **_kw: Any) -> DeliveryResult:
            return DeliveryResult.FAILED_GONE if "old" in sub.endpoint else DeliveryResult.SUCCESS

        with (
            patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True),
            patch.object(sender, "send_to_subscription", side_effect=_by_endpoint),
        ):
            result = sender.send_to_user(1, {"title": "t", "body": "b"})

        assert result is True, "1台でも成功すれば到達"
        assert {s.endpoint for s in store.get_for_user(1)} == {"https://p/new-pwa"}

    def test_zero_subscription_user_is_unreachable(self) -> None:
        """B-B1 / I-14: 購読ゼロは False (到達経路ゼロとして検知できること)。"""
        sender = WebPushSender(_config(), InMemorySubscriptionStore())
        with patch("app.notifications.push._PYWEBPUSH_AVAILABLE", True):
            assert sender.send_to_user(999, {"title": "t", "body": "b"}) is False
