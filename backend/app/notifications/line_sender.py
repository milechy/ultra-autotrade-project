"""LINE Messaging API を使った通知送信実装。"""

from __future__ import annotations

import logging

import httpx

from .schemas import NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)

LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"

# severity → プレフィックスラベル
SEVERITY_LABEL: dict[NotificationSeverity, str] = {
    NotificationSeverity.EMERGENCY: "EMERGENCY",
    NotificationSeverity.ALERT: "ALERT",
    NotificationSeverity.WARNING: "WARNING",
    NotificationSeverity.INFO: "INFO",
}


class LINENotificationSender:
    """LINE Messaging API (Push Message) 経由で通知を送信する Sender。

    NotificationSender Protocol を実装する。
    デフォルトでは ALERT および EMERGENCY のみ送信する（INFO/WARNING はスキップ）。
    送信失敗時は例外を投げずにログに残す（通知失敗でメイン処理を止めない）。
    """

    def __init__(
        self,
        channel_access_token: str,
        user_id: str,
        min_severity: NotificationSeverity = NotificationSeverity.ALERT,
    ) -> None:
        self._channel_access_token = channel_access_token
        self._user_id = user_id
        self._min_severity = min_severity
        self._timeout = 10

    def send(self, message: NotificationMessage) -> None:
        """LINE に通知を送信する。min_severity 未満は無視する。失敗時は例外を投げずにログに残す。"""
        if not self._should_send(message.severity):
            logger.debug(
                "LINE通知スキップ(severity不足): severity=%s, min=%s",
                message.severity.value,
                self._min_severity.value,
            )
            return

        text = self._format_text(message)
        payload = {
            "to": self._user_id,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._channel_access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                LINE_PUSH_API_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info(
                "LINE通知送信完了: severity=%s, title=%s",
                message.severity.value,
                message.title[:40],
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LINE通知失敗(HTTP): status=%d, title=%s",
                exc.response.status_code,
                message.title[:40],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LINE通知失敗: error=%s, title=%s",
                type(exc).__name__,
                message.title[:40],
            )

    def _should_send(self, severity: NotificationSeverity) -> bool:
        """指定された severity が送信閾値以上かどうかを判定する。"""
        severity_order = [
            NotificationSeverity.INFO,
            NotificationSeverity.WARNING,
            NotificationSeverity.ALERT,
            NotificationSeverity.EMERGENCY,
        ]
        try:
            return severity_order.index(severity) >= severity_order.index(self._min_severity)
        except ValueError:
            return False

    def _format_text(self, message: NotificationMessage) -> str:
        """LINE に送信するテキストを生成する。"""
        label = SEVERITY_LABEL.get(message.severity, message.severity.value.upper())
        return f"[{label}] {message.title}\n{message.body}"
