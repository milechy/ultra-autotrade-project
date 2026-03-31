# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""LINE Notify API を使ったHealth Factor アラート通知。

LINE Notify (https://notify-bot.line.me/) は個人トークンを使って
シンプルにメッセージを送信できるサービス。
LINE_NOTIFY_TOKEN 環境変数からトークンを読み取る。

HF閾値:
  - HF < 1.8 : WARNING (警告)
  - HF < 1.6 : EMERGENCY / HARD_STOP (緊急停止)
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

import httpx

from .schemas import NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)

LINE_NOTIFY_API_URL = "https://notify-api.line.me/api/notify"

HF_WARNING_THRESHOLD = Decimal("1.8")
HF_HARD_STOP_THRESHOLD = Decimal("1.6")

# severity → プレフィックス絵文字
SEVERITY_EMOJI: dict[NotificationSeverity, str] = {
    NotificationSeverity.INFO: "ℹ️",
    NotificationSeverity.WARNING: "⚠️",
    NotificationSeverity.ALERT: "🚨",
    NotificationSeverity.EMERGENCY: "🆘",
}


class LINENotifyClient:
    """LINE Notify API 経由でメッセージを送信するクライアント。

    NotificationSender Protocol と互換性あり。
    送信失敗時は例外を投げずにログに残す（通知失敗でメイン処理を止めない）。
    """

    def __init__(
        self,
        token: str | None = None,
        min_severity: NotificationSeverity = NotificationSeverity.WARNING,
        timeout: int = 10,
    ) -> None:
        self._token = token or os.getenv("LINE_NOTIFY_TOKEN", "")
        self._min_severity = min_severity
        self._timeout = timeout

    def send(self, message: NotificationMessage) -> None:
        """LINE Notify にメッセージを送信する。min_severity 未満はスキップ。"""
        if not self._token:
            logger.warning("LINE_NOTIFY_TOKEN が設定されていません。通知をスキップします。")
            return

        if not self._should_send(message.severity):
            logger.debug(
                "LINE Notify 通知スキップ(severity不足): severity=%s, min=%s",
                message.severity.value,
                self._min_severity.value,
            )
            return

        text = self._format_message(message)
        try:
            response = httpx.post(
                LINE_NOTIFY_API_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                data={"message": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
            logger.info(
                "LINE Notify 送信完了: severity=%s, title=%s",
                message.severity.value,
                message.title[:40],
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LINE Notify 送信失敗(HTTP): status=%d, title=%s",
                exc.response.status_code,
                message.title[:40],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LINE Notify 送信失敗: error=%s, title=%s",
                type(exc).__name__,
                message.title[:40],
            )

    def _should_send(self, severity: NotificationSeverity) -> bool:
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

    def _format_message(self, message: NotificationMessage) -> str:
        emoji = SEVERITY_EMOJI.get(message.severity, "🔔")
        return f"\n{emoji} [{message.severity.value.upper()}] {message.title}\n{message.body}"


def notify_auto_executed(
    operation: str, asset: str, amount: float, apy: float, token: str | None = None
) -> None:
    """managed/auto_execute時: 自動実行通知。"""
    from .schemas import NotificationChannel  # noqa: PLC0415

    client = LINENotifyClient(token=token)
    op_ja = "供給" if operation == "SUPPLY" else "引き出し"
    msg = NotificationMessage(
        channel=NotificationChannel.LINE,
        title="自動取引実行",
        body=f"AIが{amount:.0f} {asset}をAaveに{op_ja}しました。利回り{apy:.1f}%",
        severity=NotificationSeverity.INFO,
    )
    client.send(msg)


def notify_hf_protection(asset: str, amount: float, token: str | None = None) -> None:
    """managed/HF危険時: 資産保護通知。"""
    from .schemas import NotificationChannel  # noqa: PLC0415

    client = LINENotifyClient(token=token)
    msg = NotificationMessage(
        channel=NotificationChannel.LINE,
        title="資産保護実行",
        body=f"AIがあなたの資産を保護しました。一時的に{amount:.0f} {asset}を引き出しました",
        severity=NotificationSeverity.ALERT,
    )
    client.send(msg)


def notify_proposal_created(
    operation: str, asset: str, amount: float, token: str | None = None
) -> None:
    """active/提案作成時: 承認要求通知。"""
    from .schemas import NotificationChannel  # noqa: PLC0415

    client = LINENotifyClient(token=token)
    msg = NotificationMessage(
        channel=NotificationChannel.LINE,
        title="新しい取引提案",
        body=f"新しい取引提案: {amount:.0f} {asset} {operation}。アプリで確認→承認してください",
        severity=NotificationSeverity.WARNING,
    )
    client.send(msg)


def notify_proposal_timeout(operation: str, asset: str, token: str | None = None) -> None:
    """active/タイムアウト時: 提案キャンセル通知。"""
    from .schemas import NotificationChannel  # noqa: PLC0415

    client = LINENotifyClient(token=token)
    msg = NotificationMessage(
        channel=NotificationChannel.LINE,
        title="提案タイムアウト",
        body=f"1時間以内に承認がなかったため、{operation} {asset}の提案をキャンセルしました",
        severity=NotificationSeverity.INFO,
    )
    client.send(msg)


def notify_health_factor(health_factor: Decimal, token: str | None = None) -> None:
    """Health Factor の値に応じて LINE Notify にアラートを送信する。

    Args:
        health_factor: 現在のHealth Factor値
        token: LINE Notify トークン（省略時は環境変数 LINE_NOTIFY_TOKEN を使用）

    HF閾値ロジック:
        - HF < HF_HARD_STOP_THRESHOLD (1.6): EMERGENCY / HARD_STOP 通知
        - HF < HF_WARNING_THRESHOLD (1.8): WARNING 通知
        - HF >= 1.8: 通知しない
    """
    client = LINENotifyClient(token=token)

    if health_factor < HF_HARD_STOP_THRESHOLD:
        from .schemas import NotificationChannel

        msg = NotificationMessage(
            channel=NotificationChannel.LINE,
            severity=NotificationSeverity.EMERGENCY,
            title="HARD_STOP: Health Factor 危険域",
            body=(
                f"Health Factor が {health_factor} に低下しました（閾値: {HF_HARD_STOP_THRESHOLD}）。\n"
                "自動取引を停止しています。即座に対応してください。"
            ),
        )
        client.send(msg)
        logger.critical(
            "HF HARD_STOP 通知送信: hf=%s, threshold=%s",
            health_factor,
            HF_HARD_STOP_THRESHOLD,
        )
    elif health_factor < HF_WARNING_THRESHOLD:
        from .schemas import NotificationChannel

        msg = NotificationMessage(
            channel=NotificationChannel.LINE,
            severity=NotificationSeverity.WARNING,
            title="WARNING: Health Factor 警戒域",
            body=(
                f"Health Factor が {health_factor} に低下しました（警戒閾値: {HF_WARNING_THRESHOLD}）。\n"
                "ポジションの確認を推奨します。"
            ),
        )
        client.send(msg)
        logger.warning(
            "HF WARNING 通知送信: hf=%s, threshold=%s",
            health_factor,
            HF_WARNING_THRESHOLD,
        )
