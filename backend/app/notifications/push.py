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
from typing import Any, Optional

from pydantic import BaseModel

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


class WebPushSender:
    """Web Push (VAPID) 通知送信クラス。"""

    def __init__(self, vapid_config: VAPIDConfig, store: InMemorySubscriptionStore) -> None:
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
