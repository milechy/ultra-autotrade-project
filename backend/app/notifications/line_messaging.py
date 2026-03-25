# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/line_messaging.py
"""LINE Messaging API Flex Message 送信実装。"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"

# severity 文字列 → Flex Message ヘッダー背景色
SEVERITY_COLOR: dict[str, str] = {
    "emergency": "#FF0000",
    "alert": "#FF6B00",
    "warning": "#FFA500",
    "info": "#00B900",
}


def build_alert_flex_bubble(title: str, body: str, severity: str, color: str) -> dict:
    """Flex Message bubble dict を構築する。

    Args:
        title: バブルのタイトル（ヘッダーに表示）
        body: バブルの本文
        severity: 重要度文字列（"emergency" | "alert" | "warning" | "info"）
        color: ヘッダー背景色 (#RRGGBB 形式)

    Returns:
        LINE Flex Message 形式の dict
    """
    return {
        "type": "flex",
        "altText": title,
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": color,
                "contents": [
                    {
                        "type": "text",
                        "text": title,
                        "color": "#FFFFFF",
                        "weight": "bold",
                        "size": "md",
                    }
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": body,
                        "wrap": True,
                        "size": "sm",
                    }
                ],
            },
        },
    }


class LINEFlexMessageSender:
    """LINE Messaging API で Flex Message を送信するクラス。"""

    def __init__(self, channel_access_token: str, user_id: str) -> None:
        self._channel_access_token = channel_access_token
        self._user_id = user_id
        self._timeout = 10

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._channel_access_token}",
            "Content-Type": "application/json",
        }

    def send_flex(self, title: str, body: str, severity_str: str) -> bool:
        """Flex Message を送信する。

        Args:
            title: メッセージタイトル
            body: メッセージ本文
            severity_str: 重要度文字列

        Returns:
            送信成功なら True、失敗なら False
        """
        color = SEVERITY_COLOR.get(severity_str.lower(), "#00B900")
        flex_message = build_alert_flex_bubble(title, body, severity_str, color)

        payload = {
            "to": self._user_id,
            "messages": [flex_message],
        }

        try:
            response = httpx.post(
                LINE_PUSH_API_URL,
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info(
                "LINE Flex Message 送信完了: severity=%s, title=%s",
                severity_str,
                title[:40],
            )
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LINE Flex Message 送信失敗(HTTP): status=%d, title=%s",
                exc.response.status_code,
                title[:40],
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LINE Flex Message 送信失敗: error=%s, title=%s",
                type(exc).__name__,
                title[:40],
            )
            return False

    def send_text(self, message: str) -> bool:
        """シンプルテキストメッセージを送信する。

        Args:
            message: 送信するテキスト

        Returns:
            送信成功なら True、失敗なら False
        """
        payload = {
            "to": self._user_id,
            "messages": [
                {
                    "type": "text",
                    "text": message,
                }
            ],
        }

        try:
            response = httpx.post(
                LINE_PUSH_API_URL,
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info("LINE テキスト送信完了: message=%s", message[:40])
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LINE テキスト送信失敗(HTTP): status=%d",
                exc.response.status_code,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LINE テキスト送信失敗: error=%s",
                type(exc).__name__,
            )
            return False
