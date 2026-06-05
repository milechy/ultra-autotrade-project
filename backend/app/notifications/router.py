# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/router.py
"""Push Subscription 管理 API。"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import User
from app.database import get_db

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
# /api/notifications/* — フロントエンドおよびテストスクリプト向けエイリアス
api_router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# グローバルな subscription ストア（アプリライフタイムで保持）
_subscription_store = InMemorySubscriptionStore()


def get_subscription_store() -> InMemorySubscriptionStore:
    """グローバルな InMemorySubscriptionStore を返す。"""
    return _subscription_store


# --- リクエストスキーマ ---


class _SubscribeKeys(BaseModel):
    """ブラウザ PushSubscription の keys フィールド。"""

    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    """Push subscription 登録リクエスト。

    ブラウザ標準形式 (keys ネスト) とフラット形式の両方を受け付ける。
    """

    endpoint: str
    # フラット形式
    p256dh: str = ""
    auth: str = ""
    # ブラウザ標準形式 (PushSubscription.toJSON())
    keys: Optional[_SubscribeKeys] = None

    @model_validator(mode="after")
    def _normalize_keys(self) -> "SubscribeRequest":
        if self.keys is not None:
            self.p256dh = self.p256dh or self.keys.p256dh
            self.auth = self.auth or self.keys.auth
        return self


class TestPushRequest(BaseModel):
    """テスト Push 通知リクエスト。"""

    title: str = "テスト通知"
    body: str = "Ultra AutoTrade からのテスト通知です。"


class UnsubscribeRequest(BaseModel):
    """Push subscription 削除リクエスト。"""

    endpoint: str


# --- 共通ロジック ---


def _do_subscribe(
    req: SubscribeRequest,
    store: InMemorySubscriptionStore,
) -> dict[str, Any]:
    subscription = WebPushSubscription(
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth,
    )
    store.add(subscription)
    logger.info("Push subscription 登録: endpoint=%s", req.endpoint[:30])
    return {"status": "subscribed", "count": store.count()}


def _do_test_push(
    title: str,
    body: str,
    store: InMemorySubscriptionStore,
) -> dict[str, Any]:
    config: VAPIDConfig | None = get_vapid_config()
    if config is None:
        logger.info("VAPID 未設定のため Web Push テスト通知をスキップしました。")
        return {"sent": 0, "failed": 0, "web_push_sent": 0, "line_sent": False}

    sender = WebPushSender(vapid_config=config, store=store)
    payload = {
        "title": title,
        "body": body,
        "icon": "/icons/icon-192.png",
        "badge": "/icons/icon-192.png",
        "tag": "ultra-test",
        "requireInteraction": False,
    }
    sent = sender.send_to_all(payload)
    return {"sent": sent, "failed": 0, "web_push_sent": sent, "line_sent": False}


# --- エンドポイント ---


@router.post("/push/subscribe", status_code=status.HTTP_200_OK)
def subscribe(
    req: SubscribeRequest,
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
) -> dict[str, Any]:
    """Push subscription を登録する。認証不要（Service Worker から呼び出し可能）。"""
    return _do_subscribe(req, store)


@api_router.post("/subscribe", status_code=status.HTTP_200_OK)
def api_subscribe(
    req: SubscribeRequest,
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
) -> dict[str, Any]:
    """Push subscription を登録する（/api/notifications/subscribe エイリアス）。"""
    return _do_subscribe(req, store)


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
    req: TestPushRequest = TestPushRequest(),
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
    _current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """テスト通知を送信する。認証必須。"""
    from app.notifications.config import get_notification_settings

    result = _do_test_push(req.title, req.body, store)

    # LINE テスト通知（設定されている場合）
    settings = get_notification_settings()
    if settings.is_line_messaging_configured:
        line_sender = LINEFlexMessageSender(
            channel_access_token=settings.line_channel_access_token,
            user_id=settings.line_user_id,
        )
        line_sent = line_sender.send_text(f"Ultra AutoTrade: {req.title}")
        result["line_sent"] = line_sent
    else:
        logger.info("LINE Messaging 未設定のため LINE テスト通知をスキップしました。")

    result["status"] = "ok"
    return result


@api_router.post("/test-push", status_code=status.HTTP_200_OK)
def api_test_push(
    req: TestPushRequest,
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
    _current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """テスト通知を送信する（/api/notifications/test-push エイリアス）。認証必須。"""
    result = _do_test_push(req.title, req.body, store)
    result["status"] = "ok"
    return result


@router.get("/push/count", status_code=status.HTTP_200_OK)
def get_subscription_count(
    store: InMemorySubscriptionStore = Depends(get_subscription_store),
    _current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """登録済み subscription 数を返す。管理者のみ。"""
    return {"count": store.count()}


# ---------------------------------------------------------------------------
# 通知設定 (notification/settings)
# ---------------------------------------------------------------------------

_DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "line_enabled": True,
    "push_enabled": False,
    "preferences": {
        "ai_proposal": True,
        "execution_complete": True,
        "health_factor_warning": True,
        "emergency_stop": True,
        "monthly_report": True,
        "system_notice": True,
    },
}


class _NotificationPreferences(BaseModel):
    ai_proposal: bool = True
    execution_complete: bool = True
    health_factor_warning: bool = True
    emergency_stop: bool = True
    monthly_report: bool = True
    system_notice: bool = True


class NotificationSettingsModel(BaseModel):
    line_enabled: bool = True
    push_enabled: bool = False
    preferences: _NotificationPreferences = _NotificationPreferences()


def _get_notification_settings(user: User) -> dict[str, Any]:
    """ユーザーの通知設定を返す。未設定ならデフォルト。"""
    if user.notification_settings_json:
        try:
            parsed: dict[str, Any] = json.loads(user.notification_settings_json)
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return dict(_DEFAULT_NOTIFICATION_SETTINGS)


@router.get("/settings", status_code=status.HTTP_200_OK)
def get_notification_settings_endpoint(
    current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """ユーザーの通知設定を返す。認証必須。"""
    return _get_notification_settings(current_user)


@router.put("/settings", status_code=status.HTTP_200_OK)
def update_notification_settings_endpoint(
    body: NotificationSettingsModel,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """ユーザーの通知設定を更新する。認証必須。"""
    current_user.notification_settings_json = body.model_dump_json()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _get_notification_settings(current_user)


@api_router.get("/settings", status_code=status.HTTP_200_OK)
def api_get_notification_settings(
    current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """/api/notifications/settings GET エイリアス。"""
    return _get_notification_settings(current_user)


@api_router.put("/settings", status_code=status.HTTP_200_OK)
def api_update_notification_settings(
    body: NotificationSettingsModel,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """/api/notifications/settings PUT エイリアス。"""
    current_user.notification_settings_json = body.model_dump_json()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _get_notification_settings(current_user)
