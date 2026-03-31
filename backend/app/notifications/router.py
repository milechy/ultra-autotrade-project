# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/router.py
"""Push Subscription 管理 API。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import User

from .line_messaging import LINEFlexMessageSender
from .push import (
    InMemorySubscriptionStore,
    VAPIDConfig,
    WebPushSender,
    WebPushSubscription,
    get_vapid_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# グローバルな subscription ストア（アプリライフタイムで保持）
_subscription_store = InMemorySubscriptionStore()


def get_subscription_store() -> InMemorySubscriptionStore:
    """グローバルな InMemorySubscriptionStore を返す。"""
    return _subscription_store


# --- リクエストスキーマ ---


class SubscribeRequest(BaseModel):
    """Push subscription 登録リクエスト。"""

    endpoint: str
    p256dh: str
    auth: str


class UnsubscribeRequest(BaseModel):
    """Push subscription 削除リクエスト。"""

    endpoint: str


# --- エンドポイント ---


@router.post("/push/subscribe", status_code=status.HTTP_200_OK)
def subscribe(
    req: SubscribeRequest,
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
) -> dict[str, Any]:
    """Push subscription を登録する。認証不要（Service Worker から呼び出し可能）。"""
    subscription = WebPushSubscription(
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth,
    )
    store.add(subscription)
    logger.info("Push subscription 登録: endpoint=%s", req.endpoint[:30])
    return {"status": "subscribed", "count": store.count()}


@router.delete("/push/unsubscribe", status_code=status.HTTP_200_OK)
def unsubscribe(
    endpoint: str,
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
) -> dict[str, Any]:
    """Push subscription を削除する。認証不要。endpoint はクエリパラメータで指定する。"""
    store.remove(endpoint)
    logger.info("Push subscription 削除: endpoint=%s", endpoint[:30])
    return {"status": "unsubscribed", "count": store.count()}


@router.get("/push/vapid-key", status_code=status.HTTP_200_OK)
def get_vapid_key() -> dict[str, Any]:
    """VAPID 公開鍵を返す。VAPID 未設定の場合は null を返す。認証不要。"""
    config: VAPIDConfig | None = get_vapid_config()
    if config is None:
        return {"publicKey": None}
    return {"publicKey": config.public_key}


@router.post("/push/test", status_code=status.HTTP_200_OK)
def send_test_push(
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
    _current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """テスト通知を送信する。認証必須。"""
    from app.notifications.config import get_notification_settings

    config: VAPIDConfig | None = get_vapid_config()
    push_sent = 0
    line_sent = False

    # Web Push テスト送信
    if config is not None:
        sender = WebPushSender(vapid_config=config, store=store)
        payload = {
            "title": "テスト通知",
            "body": "Ultra AutoTrade からのテスト通知です。",
            "icon": "/icon-192.png",
            "badge": "/badge.png",
            "tag": "ultra-test",
            "requireInteraction": False,
        }
        push_sent = sender.send_to_all(payload)
    else:
        logger.info("VAPID 未設定のため Web Push テスト通知をスキップしました。")

    # LINE テスト通知（設定されている場合）
    settings = get_notification_settings()
    if settings.is_line_messaging_configured:
        line_sender = LINEFlexMessageSender(
            channel_access_token=settings.line_channel_access_token,
            user_id=settings.line_user_id,
        )
        line_sent = line_sender.send_text("Ultra AutoTrade: テスト通知")
    else:
        logger.info("LINE Messaging 未設定のため LINE テスト通知をスキップしました。")

    return {
        "status": "ok",
        "web_push_sent": push_sent,
        "line_sent": line_sent,
    }


@router.get("/push/count", status_code=status.HTTP_200_OK)
def get_subscription_count(
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """登録済み subscription 数を返す。管理者のみ。"""
    return {"count": store.count()}
