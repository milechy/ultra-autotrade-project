#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/push.py
"""Web Push (VAPID) 通知送信実装。"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    from pywebpush import WebPushException, webpush  # type: ignore

    _PYWEBPUSH_AVAILABLE = True
except ImportError:
    _PYWEBPUSH_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeliveryResult(Enum):
    """1件の Web Push 送信結果。

    2026-08-05: 以前は bool だったため「購読が失効した (410)」と「一時的に失敗した
    (タイムアウト / 5xx)」を区別できず、呼び出し側が両方まとめて購読を削除していた。
    その結果 FCM の一時障害 1 回で全ユーザーの購読が消え、ユーザーが手動で再購読する
    まで通知が永久に届かなくなる (= 到達経路が黙って失われる、本プロジェクトが
    最も避けたい失敗形)。除去してよいのは FAILED_GONE のみ。
    """

    SUCCESS = "success"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_GONE = "failed_gone"


#: 購読が恒久的に消滅したことを示す HTTP status。410 が標準、404 は実装差の吸収。
_GONE_STATUS_CODES = frozenset({404, 410})


@dataclass
class VAPIDConfig:
    """VAPID 設定。秘密鍵はログに出力しないこと。"""

    public_key: str
    private_key: str
    mailto: str


class WebPushSubscription(BaseModel):
    """Web Push サブスクリプション情報。"""

    endpoint: str
    p256dh: str
    auth: str
    # 2026-08-04 PR3: どのユーザーの購読かを紐付ける。router 側で require_active_user
    # 経由の current_user.id を必ず設定する。既存 3 フィールドのみの呼び出し (テスト等) との
    # 後方互換のため Optional のまま維持する。
    user_id: Optional[int] = None


class PushSubscriptionEntry(BaseModel):
    """users.notification_settings_json の push_subscriptions 配列 1 件分。

    WebPushSubscription から user_id を除いた形 (格納先が既にユーザーに紐づくため不要)。
    """

    endpoint: str
    p256dh: str
    auth: str


class InMemorySubscriptionStore:
    """スレッドセーフなインメモリ Push サブスクリプションストア。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # endpoint をキーとして重複を防ぐ
        self._subscriptions: dict[str, WebPushSubscription] = {}

    def add(self, subscription: WebPushSubscription) -> None:
        """サブスクリプションを追加する。同じ endpoint は上書きする。"""
        with self._lock:
            self._subscriptions[subscription.endpoint] = subscription

    def remove(self, endpoint: str) -> None:
        """指定 endpoint のサブスクリプションを削除する。存在しない場合は無視。"""
        with self._lock:
            self._subscriptions.pop(endpoint, None)

    def get_all(self) -> list[WebPushSubscription]:
        """全サブスクリプションを返す。"""
        with self._lock:
            return list(self._subscriptions.values())

    def get_for_user(self, user_id: int) -> list[WebPushSubscription]:
        """指定ユーザーのサブスクリプションのみを返す (WebPushSender.send_to_user が使用)。"""
        with self._lock:
            return [s for s in self._subscriptions.values() if s.user_id == user_id]

    def count(self) -> int:
        """登録済みサブスクリプション数を返す。"""
        with self._lock:
            return len(self._subscriptions)


class SubscriptionStore(Protocol):
    """WebPushSender が要求するストアの構造的インターフェース。

    2026-08-04 PR3: InMemorySubscriptionStore (テスト用) と DatabaseSubscriptionStore
    (本番用、DB永続化) の両方がこの形を満たす。WebPushSender 自体は変更しない。
    """

    def add(self, subscription: WebPushSubscription) -> None: ...
    def remove(self, endpoint: str) -> None: ...
    def get_all(self) -> list[WebPushSubscription]: ...
    def get_for_user(self, user_id: int) -> list[WebPushSubscription]: ...
    def count(self) -> int: ...


class DatabaseSubscriptionStore:
    """users.notification_settings_json の push_subscriptions キーに永続化するストア。

    2026-08-04 PR3: InMemorySubscriptionStore はプロセス再起動で全消失し、
    どのユーザーの購読かも分からなかった (可観測性なき握り潰しの再発パターン)。
    新規テーブルは作らず、既存の notification_settings_json (TEXT) に
    ``{"push_subscriptions": [{"endpoint", "p256dh", "auth"}, ...], ...}`` の形で
    追記する。line_enabled / push_enabled / preferences 等の他キーには一切触れない
    (raw dict レベルで push_subscriptions キーのみ読み書きする)。

    endpoint はブラウザ (オリジン) 単位でグローバルに一意という前提のため、
    同一 endpoint が別ユーザーに再登録された場合は元ユーザー側から除去する
    (同一端末でのログアウト→別アカウントでの再ログイン等、I-5/I-12 相当)。
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _read_push_subscriptions(raw_json: Optional[str]) -> list[dict[str, Any]]:
        """push_subscriptions を読む。壊れた列は空リストとして扱い、例外は投げない。

        `null` / `[1,2]` / `123` / `"str"` はいずれも json.loads が成功するため
        JSONDecodeError では捕まらない。dict 以外を弾かないと raw.get() が
        AttributeError になり、呼び出し元の except Exception に飲まれて
        「静かに配信スキップ」になる (到達経路の暗黙喪失)。
        """
        if not raw_json:
            return []
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, dict):
            return []
        subs = raw.get("push_subscriptions")
        return subs if isinstance(subs, list) else []

    @staticmethod
    def _write_push_subscriptions(raw_json: Optional[str], subs: list[dict[str, Any]]) -> str:
        """push_subscriptions のみを差し替えて返す。dict 以外の既存値は破棄して作り直す。"""
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except json.JSONDecodeError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw["push_subscriptions"] = subs
        return json.dumps(raw)

    @staticmethod
    def _parse_entry(entry: Any, user_id: int) -> Optional[WebPushSubscription]:
        """1 件の購読 entry を復元する。壊れていれば None を返し、他の購読を巻き込まない。

        entry が dict でない (文字列 / None 等) 場合 ``entry["endpoint"]`` は
        KeyError ではなく TypeError になるため、両方を弾く必要がある。
        """
        if not isinstance(entry, dict):
            return None
        try:
            return WebPushSubscription(
                endpoint=entry["endpoint"],
                p256dh=entry["p256dh"],
                auth=entry["auth"],
                user_id=user_id,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def add(self, subscription: WebPushSubscription) -> None:
        """サブスクリプションを永続化する。同じ endpoint は (他ユーザー分も含め) 上書きする。"""
        if subscription.user_id is None:
            logger.warning(
                "DatabaseSubscriptionStore.add: user_id が未設定のため保存をスキップしました "
                "(endpoint=%s)",
                subscription.endpoint[:30],
            )
            return

        from app.auth.models import User  # noqa: PLC0415

        db = self._session_factory()
        try:
            # 他ユーザーに同一 endpoint が残っていれば先に除去 (グローバル一意性の維持)。
            others = (
                db.query(User)
                .filter(
                    User.id != subscription.user_id,
                    User.notification_settings_json.isnot(None),
                )
                .all()
            )
            for other in others:
                subs = self._read_push_subscriptions(other.notification_settings_json)
                filtered = [s for s in subs if s.get("endpoint") != subscription.endpoint]
                if len(filtered) != len(subs):
                    other.notification_settings_json = self._write_push_subscriptions(
                        other.notification_settings_json, filtered
                    )

            user = db.get(User, subscription.user_id)
            if user is None:
                logger.warning(
                    "DatabaseSubscriptionStore.add: user_id=%d が見つかりません",
                    subscription.user_id,
                )
                return
            subs = self._read_push_subscriptions(user.notification_settings_json)
            subs = [s for s in subs if s.get("endpoint") != subscription.endpoint]
            subs.append(
                PushSubscriptionEntry(
                    endpoint=subscription.endpoint,
                    p256dh=subscription.p256dh,
                    auth=subscription.auth,
                ).model_dump()
            )
            user.notification_settings_json = self._write_push_subscriptions(
                user.notification_settings_json, subs
            )
            db.commit()
        finally:
            db.close()

    def remove(self, endpoint: str) -> None:
        """指定 endpoint のサブスクリプションを全ユーザーから削除する。"""
        from app.auth.models import User  # noqa: PLC0415

        db = self._session_factory()
        try:
            users = db.query(User).filter(User.notification_settings_json.isnot(None)).all()
            for user in users:
                subs = self._read_push_subscriptions(user.notification_settings_json)
                filtered = [s for s in subs if s.get("endpoint") != endpoint]
                if len(filtered) != len(subs):
                    user.notification_settings_json = self._write_push_subscriptions(
                        user.notification_settings_json, filtered
                    )
            db.commit()
        finally:
            db.close()

    def get_all(self) -> list[WebPushSubscription]:
        """全ユーザーの全サブスクリプションを返す (WebPushSender.send_to_all 用)。"""
        from app.auth.models import User  # noqa: PLC0415

        db = self._session_factory()
        try:
            users = db.query(User).filter(User.notification_settings_json.isnot(None)).all()
            result: list[WebPushSubscription] = []
            for user in users:
                for s in self._read_push_subscriptions(user.notification_settings_json):
                    parsed = self._parse_entry(s, user.id)
                    if parsed is not None:
                        result.append(parsed)
            return result
        finally:
            db.close()

    def get_for_user(self, user_id: int) -> list[WebPushSubscription]:
        """指定ユーザーのサブスクリプションのみを返す (WebPushSender.send_to_user が使用)。"""
        from app.auth.models import User  # noqa: PLC0415

        db = self._session_factory()
        try:
            user = db.get(User, user_id)
            if user is None:
                return []
            result: list[WebPushSubscription] = []
            for s in self._read_push_subscriptions(user.notification_settings_json):
                parsed = self._parse_entry(s, user_id)
                if parsed is not None:
                    result.append(parsed)
            return result
        finally:
            db.close()

    def count(self) -> int:
        """登録済みサブスクリプション総数を返す。"""
        return len(self.get_all())


class WebPushSender:
    """Web Push (VAPID) 通知送信クラス。"""

    def __init__(self, vapid_config: VAPIDConfig, store: SubscriptionStore) -> None:
        self._vapid_config = vapid_config
        self._store = store

    def send_to_all(self, payload: dict[str, Any], ttl: int = 86400) -> int:
        """全サブスクリプションに通知を送信する。成功数を返す。"""
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return 0

        subscriptions = self._store.get_all()
        success_count = 0
        failed_count = 0
        gone_endpoints: list[str] = []

        for subscription in subscriptions:
            result = self._deliver_guarded(subscription, payload, ttl)
            if result is DeliveryResult.SUCCESS:
                success_count += 1
                continue
            failed_count += 1
            if result is DeliveryResult.FAILED_GONE:
                gone_endpoints.append(subscription.endpoint)

        self._purge_gone(gone_endpoints)

        logger.info(
            "Web Push 送信完了: 成功=%d, 失敗=%d, 失効除去=%d, 合計=%d",
            success_count,
            failed_count,
            len(gone_endpoints),
            len(subscriptions),
        )
        return success_count

    def send_to_user(self, user_id: int, payload: dict[str, Any], ttl: int = 86400) -> bool:
        """特定ユーザーの全端末へ配信する。1件でも成功すれば True。購読が無ければ False。

        2026-08-04 PR5: send_to_all のユーザー限定版。AI提案通知等の per-user 配信に使う
        (send_to_all は router.py の /push/test 専用のまま変更しない)。
        """
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return False

        subscriptions = self._store.get_for_user(user_id)
        success = False
        gone_endpoints: list[str] = []

        for subscription in subscriptions:
            result = self._deliver_guarded(subscription, payload, ttl)
            if result is DeliveryResult.SUCCESS:
                success = True
            elif result is DeliveryResult.FAILED_GONE:
                gone_endpoints.append(subscription.endpoint)

        self._purge_gone(gone_endpoints)
        return success

    def _deliver_guarded(
        self, subscription: WebPushSubscription, payload: dict[str, Any], ttl: int
    ) -> DeliveryResult:
        """send_to_subscription を例外から守る。原因不明の例外は一時失敗として扱う。

        「失効と断定できない失敗」で購読を捨てないことが要件 (B-E1 / B-E2)。
        """
        try:
            return self.send_to_subscription(subscription, payload, ttl)
        except Exception:
            logger.exception(
                "Web Push 送信中に予期しないエラーが発生しました (購読は保持): endpoint=%s",
                subscription.endpoint[:30],
            )
            return DeliveryResult.FAILED_TRANSIENT

    def _purge_gone(self, gone_endpoints: list[str]) -> None:
        """失効した購読のみをストアから除去する。"""
        for endpoint in gone_endpoints:
            self._store.remove(endpoint)
            logger.info("失効した購読を除去しました: endpoint=%s", endpoint[:30])

    def send_to_subscription(
        self, subscription: WebPushSubscription, payload: dict[str, Any], ttl: int
    ) -> DeliveryResult:
        """特定のサブスクリプションに送信し、結果を3分類して返す。

        2026-08-05: 戻り値を bool から DeliveryResult に変更。呼び出し側が
        「失効 (削除すべき)」と「一時失敗 (残すべき)」を区別できるようにするため。
        """
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return DeliveryResult.FAILED_TRANSIENT

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self._vapid_config.private_key,
                vapid_claims={"sub": f"mailto:{self._vapid_config.mailto}"},
                ttl=ttl,
            )
            logger.info("Web Push 送信成功: endpoint=%s", subscription.endpoint[:30])
            return DeliveryResult.SUCCESS
        except Exception as exc:  # noqa: BLE001
            status_code: Optional[int] = None
            if _PYWEBPUSH_AVAILABLE:
                if isinstance(exc, WebPushException) and exc.response is not None:
                    status_code = exc.response.status_code

            # 404/410 のみが「購読はもう存在しない」を意味する。それ以外 (5xx / 429 /
            # ネットワーク断 / status 不明) は購読が生きている可能性があるため残す。
            if status_code in _GONE_STATUS_CODES:
                logger.info(
                    "Web Push サブスクリプション失効 (status=%s): endpoint=%s",
                    status_code,
                    subscription.endpoint[:30],
                )
                return DeliveryResult.FAILED_GONE

            logger.error(
                "Web Push 送信失敗 (一時エラー扱い・購読は保持): status=%s, endpoint=%s",
                status_code,
                subscription.endpoint[:30],
            )
            return DeliveryResult.FAILED_TRANSIENT


def push_allowed_for_user(raw_settings_json: Optional[str], preference_key: str) -> bool:
    """ユーザーの通知設定が当該種別の Web Push を許可しているか判定する。

    2026-08-05 (受け入れ条件 B-N4): 「通知設定で提案通知を無効にする → 配信されない」。
    以前は購読行が存在すれば設定を無視して送っていたため、設定画面で OFF にしても
    通知が届く状態だった (設定表示と実挙動の乖離 = 本プロジェクトが繰り返している
    ドリフトと同型)。

    push_enabled は NotificationSettingsModel 既定が False であり、
    「明示的に有効化していないユーザーには送らない」を既定の約束とする。
    設定が壊れている場合も送らない (fail-closed: 意図しない通知より無通知を選ぶ。
    到達経路ゼロ側は別途 B-6 の検知対象になる)。
    """
    if not raw_settings_json:
        return False
    try:
        raw = json.loads(raw_settings_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(raw, dict):
        return False
    if raw.get("push_enabled") is not True:
        return False
    preferences = raw.get("preferences")
    if isinstance(preferences, dict) and preferences.get(preference_key) is False:
        return False
    return True


def get_vapid_config() -> Optional[VAPIDConfig]:
    """環境変数から VAPID 設定を読み込む。未設定なら None を返す。

    VAPID_SUBJECT (例: mailto:admin@example.com) または VAPID_MAILTO を受け付ける。
    """
    public_key = os.getenv("VAPID_PUBLIC_KEY")
    private_key = os.getenv("VAPID_PRIVATE_KEY")
    # VAPID_SUBJECT (標準名) と VAPID_MAILTO (旧名) の両方をサポート
    subject = os.getenv("VAPID_SUBJECT") or os.getenv("VAPID_MAILTO")
    # "mailto:" プレフィックスは vapid_claims 内で付加するため除去
    mailto = subject.removeprefix("mailto:") if subject else None

    if not public_key or not private_key or not mailto:
        logger.debug("VAPID 設定が未設定のため Web Push は無効です。")
        return None

    return VAPIDConfig(
        public_key=public_key,
        private_key=private_key,
        mailto=mailto,
    )
