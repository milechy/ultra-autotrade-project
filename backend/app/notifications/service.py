# backend/app/notifications/service.py

"""
通知送信インターフェースと最小実装。

Phase5 のスコープでは:
- NotificationMessage を受け取る send() インターフェース
- ログ出力のみ行う LoggingNotificationSender
- 複数 Sender にファンアウトする CompositeNotificationService

を提供し、LINE/Slack などの実送信ロジックは後続フェーズで追加可能にしておく。
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Protocol

from .schemas import NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)


class NotificationSender(Protocol):
    """
    通知送信の最小インターフェース。

    実装例:
    - LoggingNotificationSender: ログ出力のみ
    - LineNotificationSender: LINE Webhook/SDK 経由で送信（将来）
    - SlackNotificationSender: Slack API 経由で送信（将来）
    """

    def send(self, message: NotificationMessage) -> None:  # pragma: no cover - Protocol
        ...


class LoggingNotificationSender:
    """
    NotificationMessage を Python の logger に記録するだけの Sender。

    - Phase5 デフォルト実装
    - 実際の外部サービスへの送信は行わない
    """

    def __init__(self, logger_: logging.Logger | None = None) -> None:
        self._logger = logger_ or logger

    def send(self, message: NotificationMessage) -> None:
        """
        通知メッセージを重要度に応じたログレベルで出力する。
        """
        prefix = f"[{message.channel.value}][{message.severity.value}] {message.title} "
        text = prefix + message.body

        if message.severity in (NotificationSeverity.EMERGENCY, NotificationSeverity.ALERT):
            self._logger.error(text)
        elif message.severity == NotificationSeverity.WARNING:
            self._logger.warning(text)
        else:
            self._logger.info(text)


class CompositeNotificationService:
    """
    複数の NotificationSender に通知をファンアウトするサービス。

    Phase5 では:
    - LoggingNotificationSender のみを持つ構成がデフォルト。
    - 後続フェーズで LINE/Slack Sender を追加する場合も、呼び出し元はこのサービスを使うだけでよい。
    """

    def __init__(self, senders: Iterable[NotificationSender]) -> None:
        self._senders: List[NotificationSender] = list(senders)

    def send(self, message: NotificationMessage) -> None:
        """
        受け取った NotificationMessage を全 Sender に送信する。
        """
        for sender in self._senders:
            try:
                sender.send(message)
            except Exception:  # noqa: BLE001 - 通知は本処理を止めない
                logger.exception("Notification sender failed. Continuing with others.")
