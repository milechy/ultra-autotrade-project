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

import logging
from typing import Optional

from .config import load_notification_settings
from .escalation import SlackEscalationSender
from .line_sender import LINENotificationSender
from .schemas import NotificationChannel, NotificationMessage, NotificationSeverity
from .service import (
    CompositeNotificationService,
    DatabaseNotificationSender,
    LoggingNotificationSender,
)
from .slack_sender import SlackNotificationSender
from .twilio_sender import TwilioSender

logger = logging.getLogger(__name__)

_notification_service: Optional[CompositeNotificationService] = None


def get_notification_service() -> CompositeNotificationService:
    """
    アプリ全体で共有する CompositeNotificationService を返す。

    初回呼び出し時にのみ生成し、それ以降は同じインスタンスを返す。

    Slack が設定されている場合、SlackEscalationSender でラップして
    5 連続失敗時に Twilio 電話エスカレーションを行う。
    """
    global _notification_service
    if _notification_service is None:
        senders: list[
            LoggingNotificationSender
            | SlackEscalationSender
            | SlackNotificationSender
            | LINENotificationSender
            | DatabaseNotificationSender
        ] = []

        logging_sender = LoggingNotificationSender()
        senders.append(logging_sender)

        settings = load_notification_settings()

        # Twilio sender（Slack エスカレーション用）
        twilio_sender: Optional[TwilioSender] = None
        if settings.is_twilio_configured:
            twilio_sender = TwilioSender(
                account_sid=settings.twilio_account_sid,  # type: ignore[arg-type]
                auth_token=settings.twilio_auth_token,  # type: ignore[arg-type]
                from_number=settings.twilio_from_number,  # type: ignore[arg-type]
                to_number=settings.twilio_oncall_phone,  # type: ignore[arg-type]
                oncall_start_hour=settings.oncall_start_hour,
                oncall_end_hour=settings.oncall_end_hour,
            )
            logger.info(
                "TwilioSender: 設定済み (オンコール時間 JST %d:00-%d:00)。",
                settings.oncall_start_hour,
                settings.oncall_end_hour,
            )
        else:
            logger.info("TwilioSender: 環境変数未設定。電話エスカレーション無効。")

        if settings.is_slack_configured and settings.slack_webhook_url:
            raw_slack = SlackNotificationSender(webhook_url=settings.slack_webhook_url)
            # Slack をエスカレーションラッパーで包む
            escalation_sender = SlackEscalationSender(
                slack_sender=raw_slack,
                twilio_sender=twilio_sender,
                escalation_threshold=settings.escalation_threshold,
                cooldown_minutes=settings.escalation_cooldown_minutes,
            )
            senders.append(escalation_sender)

        if settings.is_line_messaging_configured:
            line_sender = LINENotificationSender(
                channel_access_token=settings.line_channel_access_token,
                user_id=settings.line_user_id,
            )
            senders.append(line_sender)

        # DB永続化: SessionLocal が利用可能な場合のみ追加（テスト環境では上書き可能）
        try:
            from app.database import SessionLocal

            db_sender = DatabaseNotificationSender(SessionLocal)
            senders.append(db_sender)
        except Exception:  # noqa: BLE001
            logger.warning(
                "DatabaseNotificationSender: could not load SessionLocal, DB logging disabled."
            )

        _notification_service = CompositeNotificationService(senders)
    return _notification_service


def reset_notification_service() -> None:
    """通知サービスをリセットする（テスト用）。"""
    global _notification_service
    _notification_service = None


__all__ = [
    "NotificationChannel",
    "NotificationSeverity",
    "NotificationMessage",
    "CompositeNotificationService",
    "LoggingNotificationSender",
    "SlackNotificationSender",
    "SlackEscalationSender",
    "LINENotificationSender",
    "TwilioSender",
    "get_notification_service",
    "reset_notification_service",
]
