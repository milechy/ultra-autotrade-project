# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
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

import asyncio
import logging
from typing import Any, Iterable, List, Protocol

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


class DatabaseNotificationSender:
    """
    通知を notification_logs テーブルに保存する Sender。

    SessionLocal（sessionmaker）を受け取り、send() 毎に新しい Session を開いて
    コミット後にクローズする。失敗しても本処理を止めない（fail-open）。
    """

    def __init__(self, session_factory: object) -> None:
        # session_factory: sqlalchemy.orm.sessionmaker (型をここではAnyで扱う、循環import回避)
        self._session_factory = session_factory

    def send(self, message: NotificationMessage) -> None:
        from app.notifications.models import NotificationLog  # 循環import回避

        try:
            db = self._session_factory()
            try:
                log = NotificationLog(
                    channel=message.channel.value,
                    severity=message.severity.value,
                    title=message.title,
                    body=message.body,
                    partner_id=message.partner_id,
                    user_id=message.user_id,
                    created_at=message.created_at,
                )
                db.add(log)
                db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("DatabaseNotificationSender: failed to persist notification log.")


class DualChannelNotificationService:
    """
    LINE Flex Message + Web Push の dual-channel 通知サービス（Phase 3）。

    send() は両チャンネルへの送信を試み、各結果を dict で返す。
    一方が失敗してももう一方は継続する（fail-open）。
    """

    def __init__(
        self,
        line_sender: Any,  # LINEFlexMessageSender | None
        push_sender: Any,  # WebPushSender | None
    ) -> None:
        self._line_sender = line_sender
        self._push_sender = push_sender

    async def send_line(self, payload: Any) -> dict[str, Any] | None:
        """LINE Flex Message を送信する。未設定または失敗時は None を返す。"""
        if self._line_sender is None:
            logger.debug("LINE sender not configured, skipping.")
            return None
        try:
            # LINEFlexMessageSender.send_flex() は同期なので asyncio.to_thread でラップ
            success = await asyncio.to_thread(
                self._line_sender.send_flex,
                payload.title,
                payload.body,
                payload.severity,
            )
            return {"sent": success}
        except Exception as exc:  # noqa: BLE001
            logger.error("LINE notification failed: %s", exc)
            return None

    async def send_web_push(self, payload: Any, user_wallet: str) -> dict[str, Any] | None:
        """Web Push を全 subscription に送信する。未設定または失敗時は None を返す。"""
        if self._push_sender is None:
            logger.debug("Web Push sender not configured, skipping.")
            return None
        try:
            sent_count = await asyncio.to_thread(
                self._push_sender.send_to_all,
                payload.web_push_payload,
            )
            return {"sent_count": sent_count, "wallet": user_wallet[:8] + "..."}
        except Exception as exc:  # noqa: BLE001
            logger.error("Web Push notification failed: %s", exc)
            return None

    async def send(self, payload: Any, user_wallet: str) -> dict[str, Any]:
        """
        LINE + Web Push の両チャンネルに通知を送信する。

        Args:
            payload: NotificationPayload (templates.py)
            user_wallet: ユーザーウォレットアドレス（Web Push対象特定用）

        Returns:
            {"line": result | None, "web_push": result | None}
        """
        results: dict[str, Any] = {"line": None, "web_push": None}

        # LINE通知
        try:
            line_result = await self.send_line(payload)
            results["line"] = line_result
        except Exception as e:  # noqa: BLE001
            logger.error("LINE notification failed: %s", e)

        # Web Push通知
        try:
            push_result = await self.send_web_push(payload, user_wallet)
            results["web_push"] = push_result
        except Exception as e:  # noqa: BLE001
            logger.error("Web Push notification failed: %s", e)

        return results
