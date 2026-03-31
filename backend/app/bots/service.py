# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from app.automation.schemas import ComponentType
from app.automation.state import get_monitoring_service

from .client import OctoBotClient, OctoBotClientError
from .schemas import (
    OctoBotSignal,
    OctoBotSignalDetail,
    OctoBotSignalRequest,
    OctoBotSignalResponse,
    OctoBotSignalStatus,
)

logger = logging.getLogger(__name__)


class OctoBotService:
    """
    AIAnalysisResult 相当の入力から、OctoBot 外部 API 向けシグナルを生成・送信するサービス層。

    責務:
    - 信頼度しきい値に基づくスキップ
    - 1時間あたり同一アクションのレート制限
    - OctoBotClient への実際の送信
    - MonitoringService へのトレード記録（過剰取引監視向け）
    """

    def __init__(
        self,
        client: OctoBotClient,
        *,
        min_confidence: int = 70,
        max_same_action_per_hour: int = 10,
    ) -> None:
        self._client = client
        self._min_confidence = int(min_confidence)
        self._max_same_action_per_hour = int(max_same_action_per_hour)
        self._recent_actions: List[Tuple[str, datetime]] = []
        self._monitoring = get_monitoring_service()

    # ---- 内部ヘルパー -------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _cleanup_recent_actions(self, now: datetime) -> None:
        window_start = now - timedelta(hours=1)
        self._recent_actions = [
            (action, ts) for action, ts in self._recent_actions if ts >= window_start
        ]

    def _count_same_action_recent(self, action: str, now: datetime) -> int:
        self._cleanup_recent_actions(now)
        return sum(1 for a, _ in self._recent_actions if a == action)

    # ---- 公開 API ------------------------------------------------------

    def process_signals(self, request: OctoBotSignalRequest) -> OctoBotSignalResponse:
        """
        OctoBotSignalRequest を処理して、OctoBotSignalResponse を返すメイン処理。
        """
        details: List[OctoBotSignalDetail] = []
        success_count = 0
        skipped_count = 0
        failed_count = 0

        for signal in request.signals:
            # timestamp が未指定の場合は現在時刻を使う
            ts = getattr(signal, "timestamp", None) or self._now()

            # TradeAction Enum / str の両方に対応
            action_val = (
                signal.action.value if hasattr(signal.action, "value") else str(signal.action)
            )

            # 1. 信頼度しきい値チェック
            if signal.confidence < self._min_confidence:
                logger.info(
                    "Signal skipped: confidence below threshold",
                    extra={
                        "signal_id": signal.id,
                        "action": action_val,
                        "confidence": signal.confidence,
                        "threshold": self._min_confidence,
                        "status": "SKIPPED",
                    },
                )
                details.append(
                    OctoBotSignalDetail(
                        id=signal.id,
                        status=OctoBotSignalStatus.SKIPPED,
                        message="skipped: confidence below threshold",
                    )
                )
                skipped_count += 1
                # 過剰取引の観点では「実行されていない」ので MonitoringService に記録しない
                continue

            # 2. 1時間あたり同一アクションのレート制限
            if self._max_same_action_per_hour > 0:
                current_count = self._count_same_action_recent(action_val, ts)
                if current_count >= self._max_same_action_per_hour:
                    logger.warning(
                        "Signal skipped: rate limit exceeded for same action per hour",
                        extra={
                            "signal_id": signal.id,
                            "action": action_val,
                            "confidence": signal.confidence,
                            "current_count": current_count,
                            "limit": self._max_same_action_per_hour,
                            "status": "SKIPPED",
                        },
                    )
                    details.append(
                        OctoBotSignalDetail(
                            id=signal.id,
                            status=OctoBotSignalStatus.SKIPPED,
                            message="skipped: rate limit for same action per hour",
                        )
                    )
                    skipped_count += 1
                    # 実際には送信していないが、「シグナルが多すぎる」という意味で MonitoringService に記録しておく
                    self._monitoring.record_trade(
                        ComponentType.OCTOBOT,
                        action_val,
                        at=ts,
                    )
                    continue

            # 3. 実際の送信
            try:
                self._send_to_octobot(signal)
            except OctoBotClientError as exc:
                logger.error(
                    "Signal send failed: OctoBot API error",
                    extra={
                        "signal_id": signal.id,
                        "action": action_val,
                        "confidence": signal.confidence,
                        "error": str(exc),
                        "status": "FAILED",
                    },
                )
                details.append(
                    OctoBotSignalDetail(
                        id=signal.id,
                        status=OctoBotSignalStatus.FAILED,
                        message=str(exc),
                    )
                )
                failed_count += 1
                continue

            # 成功時
            logger.info(
                "Signal sent successfully",
                extra={
                    "signal_id": signal.id,
                    "action": action_val,
                    "confidence": signal.confidence,
                    "status": "SENT",
                },
            )
            self._recent_actions.append((action_val, ts))
            details.append(
                OctoBotSignalDetail(
                    id=signal.id,
                    status=OctoBotSignalStatus.SENT,
                    message="signal sent",
                )
            )
            success_count += 1

            # MonitoringService にトレード（シグナル）を記録
            self._monitoring.record_trade(
                ComponentType.OCTOBOT,
                action_val,
                at=ts,
            )

        # 処理サマリログ
        total_count = success_count + skipped_count + failed_count
        logger.info(
            "Signal processing completed",
            extra={
                "total": total_count,
                "sent": success_count,
                "skipped": skipped_count,
                "failed": failed_count,
            },
        )

        return OctoBotSignalResponse(
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            details=details,
        )

    # ---- 内部: 実際の HTTP 呼び出し -----------------------------------

    def _send_single_signal(self, signal: OctoBotSignal) -> None:
        """
        OctoBotClient に実際のシグナル送信を行う。

        外部 API には最小限の情報のみを渡す:
        { action, confidence, reason, timestamp } のみ。
        """
        # TradeAction が Enum の場合と素の str の場合両方に対応
        action_val = signal.action.value if hasattr(signal.action, "value") else str(signal.action)

        ts = getattr(signal, "timestamp", None) or self._now()

        payload = {
            "action": action_val,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "timestamp": ts.isoformat(),
        }
        self._client.send_signal(payload)

    def _send_to_octobot(self, signal: OctoBotSignal) -> None:
        """
        後方互換用（テストが monkeypatch するフック）。
        実送信の実装に委譲する。
        """
        # このクラスの実送信は _send_single_signal に集約されているため、そこへ委譲する
        return self._send_single_signal(signal)
