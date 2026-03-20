# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/factory.py

"""
通知サービスの簡易ファクトリ。

Phase5 時点では:
- LoggingNotificationSender のみを登録した CompositeNotificationService を返す。
- 将来、設定や環境変数に応じて LINE/Slack Sender を追加する拡張余地を残す。
"""

from __future__ import annotations

from typing import Optional

from .config import load_notification_settings
from .line_sender import LINENotificationSender
from .schemas import NotificationChannel, NotificationMessage, NotificationSeverity
from .service import CompositeNotificationService, LoggingNotificationSender
from .slack_sender import SlackNotificationSender

_notification_service: Optional[CompositeNotificationService] = None


def get_notification_service() -> CompositeNotificationService:
    """
    アプリ全体で共有する CompositeNotificationService を返す。

    初回呼び出し時にのみ生成し、それ以降は同じインスタンスを返す。
    """
    global _notification_service
    if _notification_service is None:
        senders: list[
            LoggingNotificationSender | SlackNotificationSender | LINENotificationSender
        ] = []

        logging_sender = LoggingNotificationSender()
        senders.append(logging_sender)

        settings = load_notification_settings()
        if settings.is_slack_configured and settings.slack_webhook_url:
            slack_sender = SlackNotificationSender(webhook_url=settings.slack_webhook_url)
            senders.append(slack_sender)

        if settings.is_line_messaging_configured:
            line_sender = LINENotificationSender(
                channel_access_token=settings.line_channel_access_token,
                user_id=settings.line_user_id,
            )
            senders.append(line_sender)

        _notification_service = CompositeNotificationService(senders)
    return _notification_service


__all__ = [
    "NotificationChannel",
    "NotificationSeverity",
    "NotificationMessage",
    "CompositeNotificationService",
    "LoggingNotificationSender",
    "SlackNotificationSender",
    "LINENotificationSender",
    "get_notification_service",
]
