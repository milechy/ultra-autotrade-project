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
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    from pywebpush import WebPushException, webpush  # type: ignore

    _PYWEBPUSH_AVAILABLE = True
except ImportError:
    _PYWEBPUSH_AVAILABLE = False

logger = logging.getLogger(__name__)


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
        if not raw_json:
            return []
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError:
            return []
        subs = raw.get("push_subscriptions")
        return subs if isinstance(subs, list) else []

    @staticmethod
    def _write_push_subscriptions(raw_json: Optional[str], subs: list[dict[str, Any]]) -> str:
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except json.JSONDecodeError:
            raw = {}
        raw["push_subscriptions"] = subs
        return json.dumps(raw)

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
                    try:
                        result.append(
                            WebPushSubscription(
                                endpoint=s["endpoint"],
                                p256dh=s["p256dh"],
                                auth=s["auth"],
                                user_id=user.id,
                            )
                        )
                    except KeyError:
                        continue
            return result
        finally:
            db.close()

    def get_for_user(self, user_id: int) -> list[WebPushSubscription]:
        """指定ユーザーのサブスクリプションのみを返す (PR5: per-user 配信で使用予定)。"""
        from app.auth.models import User  # noqa: PLC0415

        db = self._session_factory()
        try:
            user = db.get(User, user_id)
            if user is None:
                return []
            result: list[WebPushSubscription] = []
            for s in self._read_push_subscriptions(user.notification_settings_json):
                try:
                    result.append(
                        WebPushSubscription(
                            endpoint=s["endpoint"],
                            p256dh=s["p256dh"],
                            auth=s["auth"],
                            user_id=user_id,
                        )
                    )
                except KeyError:
                    continue
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
        failed_endpoints: list[str] = []

        for subscription in subscriptions:
            try:
                ok = self.send_to_subscription(subscription, payload, ttl)
                if ok:
                    success_count += 1
                else:
                    failed_endpoints.append(subscription.endpoint)
            except Exception:
                logger.exception(
                    "Web Push 送信中に予期しないエラーが発生しました: endpoint=%s",
                    subscription.endpoint[:30],
                )
                failed_endpoints.append(subscription.endpoint)

        # 失敗した subscription を削除
        for endpoint in failed_endpoints:
            self._store.remove(endpoint)
            logger.info("失敗したサブスクリプションを削除しました: endpoint=%s", endpoint[:30])

        logger.info(
            "Web Push 送信完了: 成功=%d, 失敗=%d, 合計=%d",
            success_count,
            len(failed_endpoints),
            len(subscriptions),
        )
        return success_count

    def send_to_subscription(
        self, subscription: WebPushSubscription, payload: dict[str, Any], ttl: int
    ) -> bool:
        """特定のサブスクリプションに通知を送信する。成功した場合は True を返す。"""
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return False

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
            return True
        except Exception as exc:  # noqa: BLE001
            # 410 Gone はサブスクリプションが無効（削除すべき）
            status_code: Optional[int] = None
            if _PYWEBPUSH_AVAILABLE:
                if isinstance(exc, WebPushException) and exc.response is not None:
                    status_code = exc.response.status_code

            if status_code == 410:
                logger.info(
                    "Web Push サブスクリプションが無効 (410 Gone): endpoint=%s",
                    subscription.endpoint[:30],
                )
            else:
                logger.error(
                    "Web Push 送信失敗: status=%s, endpoint=%s",
                    status_code,
                    subscription.endpoint[:30],
                )
            return False


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
