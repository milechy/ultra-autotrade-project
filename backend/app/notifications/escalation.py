# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Slack 連続失敗 → Twilio 電話エスカレーションサービス。

設計原則:
- 1人プロジェクト前提: オペレーターへの確認ループなし、自動判断で電話
- Slack N 連続 FAIL (デフォルト 5) で ALERT/EMERGENCY を電話エスカレーション
- クールダウン (デフォルト 30 分) で繰り返し電話を防ぐ
- 自動復旧検知で連続カウントをリセット

オンコール時間帯定義 (JST):
    9:00 - 22:00  : プライム帯 → 音声電話（応答必須）
    22:00 - 翌9:00: オフ帯 → SMS のみ（ベストエフォート、起床時確認）
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .schemas import NotificationChannel, NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)

# デフォルト値
DEFAULT_ESCALATION_THRESHOLD = 5
DEFAULT_COOLDOWN_MINUTES = 30


class EscalationState:
    """エスカレーション状態をスレッドセーフに管理する。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._last_escalation_at: Optional[datetime] = None
        self._last_success_at: Optional[datetime] = None

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def record_failure(self) -> int:
        """Slack 送信失敗を記録し、現在の連続失敗数を返す。"""
        with self._lock:
            self._consecutive_failures += 1
            return self._consecutive_failures

    def record_success(self) -> None:
        """Slack 送信成功を記録し、連続失敗カウントをリセットする。"""
        with self._lock:
            self._consecutive_failures = 0
            self._last_success_at = datetime.now(timezone.utc)

    def try_escalate(self, cooldown_minutes: int) -> bool:
        """エスカレーション実行フラグを取得する（クールダウン考慮）。

        クールダウン内なら False を返し、重複発信を防ぐ。
        実行可能なら最終エスカレーション時刻を更新して True を返す。
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._last_escalation_at is not None:
                elapsed = now - self._last_escalation_at
                if elapsed < timedelta(minutes=cooldown_minutes):
                    remaining = int(
                        (timedelta(minutes=cooldown_minutes) - elapsed).total_seconds() / 60
                    )
                    logger.info(
                        "EscalationService: クールダウン中（残 %d 分）。エスカレーションスキップ。",
                        remaining,
                    )
                    return False
            self._last_escalation_at = now
            return True


class SlackEscalationSender:
    """Slack 送信失敗を監視し、閾値超過で Twilio に電話エスカレーションするラッパー。

    既存の SlackNotificationSender を内部に持ち、失敗カウントを追跡する。
    Slack が N 連続失敗した場合、TwilioSender 経由で ALERT を電話に昇格する。
    """

    def __init__(
        self,
        slack_sender: Any,  # SlackNotificationSender（循環 import 回避のため Any 型）
        twilio_sender: Any,  # TwilioSender | None
        escalation_threshold: int = DEFAULT_ESCALATION_THRESHOLD,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
        state: Optional[EscalationState] = None,
    ) -> None:
        self._slack = slack_sender
        self._twilio = twilio_sender
        self._threshold = escalation_threshold
        self._cooldown_minutes = cooldown_minutes
        self._state = state or EscalationState()

    def send(self, message: NotificationMessage) -> None:
        """Slack に通知を送信し、連続失敗時はエスカレーションする。"""
        slack_ok = self._try_slack(message)

        if slack_ok:
            self._state.record_success()
            return

        failures = self._state.record_failure()
        logger.warning(
            "EscalationService: Slack 送信失敗 (%d 連続 / 閾値 %d)。",
            failures,
            self._threshold,
        )

        if failures >= self._threshold:
            self._escalate(message, failures)

    def _try_slack(self, message: NotificationMessage) -> bool:
        """Slack 送信を試みる。成功: True、失敗: False。"""
        try:
            self._slack.send(message)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("EscalationService: Slack 送信例外 error=%s", type(exc).__name__)
            return False

    def _escalate(self, message: NotificationMessage, failures: int) -> None:
        """Twilio 電話/SMS でエスカレーションする。"""
        if self._twilio is None:
            logger.error(
                "EscalationService: Twilio 未設定。Slack %d 連続失敗だが電話エスカレーション不可。",
                failures,
            )
            return

        if not self._state.try_escalate(self._cooldown_minutes):
            return

        escalation_msg = NotificationMessage(
            channel=NotificationChannel.PHONE,
            severity=NotificationSeverity.EMERGENCY,
            title=f"[要対応] Slack {failures}連続失敗: {message.title}",
            body=(
                f"Ultra AutoTrade 緊急アラート。\n"
                f"Slack が {failures} 回連続で失敗しました。\n"
                f"元メッセージ: {message.body[:100]}"
            ),
        )
        logger.error(
            "EscalationService: Twilio 電話エスカレーション実行 (Slack %d 連続失敗)。",
            failures,
        )
        try:
            self._twilio.send(escalation_msg)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "EscalationService: Twilio エスカレーション失敗 error=%s",
                type(exc).__name__,
            )
