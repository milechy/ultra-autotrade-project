# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Slack Incoming Webhook を使った通知送信実装。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .schemas import NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)

# severity → Slack emoji マッピング
SEVERITY_EMOJI: dict[NotificationSeverity, str] = {
    NotificationSeverity.INFO: ":information_source:",
    NotificationSeverity.WARNING: ":warning:",
    NotificationSeverity.ALERT: ":rotating_light:",
    NotificationSeverity.EMERGENCY: ":sos:",
}

# severity → Slack attachment color
SEVERITY_COLOR: dict[NotificationSeverity, str] = {
    NotificationSeverity.INFO: "#36a64f",
    NotificationSeverity.WARNING: "#ff9800",
    NotificationSeverity.ALERT: "#f44336",
    NotificationSeverity.EMERGENCY: "#b71c1c",
}


class SlackNotificationSender:
    """Slack Incoming Webhook 経由で通知を送信する Sender。

    NotificationSender Protocol を実装する。
    送信失敗時は例外を投げずにログに残す（通知失敗でメイン処理を止めない）。
    """

    def __init__(self, webhook_url: str, timeout_seconds: int = 10) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds

    def send(self, message: NotificationMessage) -> None:
        """Slack に通知を送信する。失敗時は例外を投げずにログに残す。"""
        payload = self._build_payload(message)
        try:
            response = httpx.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info(
                "Slack通知送信完了: severity=%s, title=%s",
                message.severity.value,
                message.title[:40],
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Slack通知失敗(HTTP): status=%d, title=%s",
                exc.response.status_code,
                message.title[:40],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Slack通知失敗: error=%s, title=%s",
                type(exc).__name__,
                message.title[:40],
            )

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Slack Block Kit ペイロードを生成する。"""
        emoji = SEVERITY_EMOJI.get(message.severity, ":bell:")
        color = SEVERITY_COLOR.get(message.severity, "#cccccc")
        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"{emoji} *{message.title}*",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": message.body,
                            },
                        },
                    ],
                }
            ]
        }
