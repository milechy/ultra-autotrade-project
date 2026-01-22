# backend/tests/test_notifications_service.py

import logging
from typing import List

from app.notifications.schemas import NotificationChannel, NotificationMessage, NotificationSeverity
from app.notifications.service import (
    CompositeNotificationService,
    LoggingNotificationSender,
)


def test_logging_notification_sender_uses_correct_log_level(caplog) -> None:
    """
    LoggingNotificationSender が severity に応じたログレベルで出力することを確認。
    """
    logger = logging.getLogger("test_logger_notifications")
    sender = LoggingNotificationSender(logger_=logger)

    message_info = NotificationMessage(
        channel=NotificationChannel.INTERNAL_LOG,
        severity=NotificationSeverity.INFO,
        title="info-title",
        body="info-body",
    )
    message_warn = NotificationMessage(
        channel=NotificationChannel.INTERNAL_LOG,
        severity=NotificationSeverity.WARNING,
        title="warn-title",
        body="warn-body",
    )
    message_err = NotificationMessage(
        channel=NotificationChannel.INTERNAL_LOG,
        severity=NotificationSeverity.EMERGENCY,
        title="em-title",
        body="em-body",
    )

    with caplog.at_level(logging.INFO, logger="test_logger_notifications"):
        sender.send(message_info)
        sender.send(message_warn)
        sender.send(message_err)

    # message_info/info-body が INFO レベルで出力されていること
    info_records = [
        r for r in caplog.records if r.levelno == logging.INFO and "info-body" in r.getMessage()
    ]
    assert info_records, "INFO log should contain 'info-body'"

    # WARNING
    warn_records = [
        r for r in caplog.records if r.levelno == logging.WARNING and "warn-body" in r.getMessage()
    ]
    assert warn_records, "WARNING log should contain 'warn-body'"

    # ERROR (EMERGENCY/ALERT)
    err_records = [
        r for r in caplog.records if r.levelno == logging.ERROR and "em-body" in r.getMessage()
    ]
    assert err_records, "ERROR log should contain 'em-body'"


class DummySender:
    def __init__(self) -> None:
        self.messages: List[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        self.messages.append(message)


def test_composite_notification_service_fanout() -> None:
    """
    CompositeNotificationService が複数 Sender に対して send() を呼び出すことを確認。
    """
    sender1 = DummySender()
    sender2 = DummySender()
    service = CompositeNotificationService([sender1, sender2])

    msg = NotificationMessage(
        channel=NotificationChannel.INTERNAL_LOG,
        severity=NotificationSeverity.INFO,
        title="test",
        body="hello",
    )

    service.send(msg)

    assert sender1.messages == [msg]
    assert sender2.messages == [msg]
