# backend/app/notifications/factory.py

"""
通知サービスの簡易ファクトリ。

Phase5 時点では:
- LoggingNotificationSender のみを登録した CompositeNotificationService を返す。
- 将来、設定や環境変数に応じて LINE/Slack Sender を追加する拡張余地を残す。
"""

from __future__ import annotations

from typing import Optional

from .schemas import NotificationChannel, NotificationSeverity, NotificationMessage
from .service import CompositeNotificationService, LoggingNotificationSender

_notification_service: Optional[CompositeNotificationService] = None


def get_notification_service() -> CompositeNotificationService:
    """
    アプリ全体で共有する CompositeNotificationService を返す。

    初回呼び出し時にのみ生成し、それ以降は同じインスタンスを返す。
    """
    global _notification_service
    if _notification_service is None:
        logging_sender = LoggingNotificationSender()
        _notification_service = CompositeNotificationService([logging_sender])
    return _notification_service


__all__ = [
    "NotificationChannel",
    "NotificationSeverity",
    "NotificationMessage",
    "CompositeNotificationService",
    "LoggingNotificationSender",
    "get_notification_service",
]
