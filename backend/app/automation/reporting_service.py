# backend/app/automation/reporting_service.py

"""
MonitoringService が蓄積したメトリクスを元に、
日次 / 週次のサマリーレポートを生成するサービス。

責務:
- 対象期間（daily / weekly）の決定
- MonitoringService からイベント・ヘルスファクター履歴を取得
- 集計して AutomationReportSummary を返す

ここでは外部 I/O（Notion・ファイル・通知など）は一切行わず、
純粋に「集計ロジック」に限定する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel

from .monitoring_service import MonitoringService
from .schemas import (
    AlertLevel,
    AutomationReportSummary,
    MetricAggregate,
    ReportPeriod,
)

from .state import get_monitoring_service
from app.notifications.schemas import (
    NotificationChannel,
    NotificationMessage,
    NotificationSeverity,
)

class MetricsSummary(BaseModel):
    """単純なメトリクスサマリ（最小限）。"""

    period_start: datetime
    period_end: datetime
    # metric_id -> (min, max, avg, count)
    stats: Dict[str, Dict[str, float]]


def build_metrics_summary(
    events: Iterable[MonitoringEvent],
    *,
    now: datetime | None = None,
    period: timedelta = timedelta(days=1),
) -> MetricsSummary:
    """MonitoringEvent 群からメトリクスサマリを構築する。

    - metric が None のイベントは無視する
    - metric_id ごとに min/max/avg/count を算出する
    """

    now = now or datetime.utcnow()
    period_start = now - period

    sums: Dict[str, float] = defaultdict(float)
    mins: Dict[str, float] = {}
    maxs: Dict[str, float] = {}
    counts: Dict[str, int] = defaultdict(int)

    for event in events:
        if event.metric is None:
            continue

        metric: MetricPoint = event.metric
        if metric.recorded_at < period_start or metric.recorded_at > now:
            continue

        mid = metric.metric_id
        val = metric.value

        sums[mid] += val
        counts[mid] += 1

        if mid not in mins or val < mins[mid]:
            mins[mid] = val
        if mid not in maxs or val > maxs[mid]:
            maxs[mid] = val

    stats: Dict[str, Dict[str, float]] = {}
    for mid, total in sums.items():
        cnt = counts[mid]
        stats[mid] = {
            "min": mins[mid],
            "max": maxs[mid],
            "avg": total / cnt if cnt else 0.0,
            "count": float(cnt),
        }

    return MetricsSummary(
        period_start=period_start,
        period_end=now,
        stats=stats,
    )

class ReportingService:
    """
    監視結果を集計してレポートサマリを生成するサービス。

    将来的に:
    - AI による自然言語レポート生成
    - Notion への書き込み
    - 通知サービスへの送信
    などの「上位レイヤー」から再利用される想定。
    """

    def __init__(self, monitoring: Optional[MonitoringService] = None) -> None:
        self._monitoring: MonitoringService = monitoring or get_monitoring_service()

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_now(now: Optional[datetime]) -> datetime:
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now

    @staticmethod
    def _get_period_range(period: ReportPeriod, now: datetime) -> tuple[datetime, datetime]:
        """
        period（daily/weekly）に応じて集計対象期間を決定する。

        - DAILY: 当日 00:00:00 〜 now
        - WEEKLY: now から遡って 7日間
        """
        if period == ReportPeriod.DAILY:
            start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=now.tzinfo)
            end = now
        elif period == ReportPeriod.WEEKLY:
            start = now - timedelta(days=7)
            end = now
        else:
            # 将来拡張用。現時点では DAILY と同じ扱いにする。
            start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=now.tzinfo)
            end = now
        return start, end

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def generate_summary_report(
        self,
        period: ReportPeriod,
        *,
        now: Optional[datetime] = None,
    ) -> AutomationReportSummary:
        """
        指定された期間（daily/weekly）のサマリーレポートを生成する。
        """
        now_norm = self._normalize_now(now)
        from_ts, to_ts = self._get_period_range(period, now_norm)

        # 1. イベント件数の集計
        events = self._monitoring.get_events_in_range(from_ts, to_ts)
        total_events = len(events)

        level_counts: Dict[AlertLevel, int] = {level: 0 for level in AlertLevel}
        for event in events:
            # AlertLevel に存在しない値の場合でも落ちないよう get(..., 0)
            level_counts[event.level] = level_counts.get(event.level, 0) + 1

        emergency_occurred = level_counts.get(AlertLevel.EMERGENCY, 0) > 0

        # 2. メトリクスの集計（ダッシュボード / レポート向け）
        metric_values: Dict[str, List[Decimal]] = {}
        metric_last: Dict[str, Decimal] = {}
        metric_units: Dict[str, Optional[str]] = {}

        for event in events:
            metric = event.metric
            if metric is None:
                continue

            mid = metric.metric_id
            value = metric.value

            metric_values.setdefault(mid, []).append(value)
            metric_last[mid] = value
            if mid not in metric_units or metric_units[mid] is None:
                metric_units[mid] = metric.unit

        metric_aggregates: Dict[str, MetricAggregate] = {}
        for mid, values in metric_values.items():
            count = len(values)
            min_v: Optional[Decimal] = min(values) if values else None
            max_v: Optional[Decimal] = max(values) if values else None
            last_v: Optional[Decimal] = metric_last.get(mid)

            if values:
                total = sum(values, Decimal("0"))
                avg_v: Optional[Decimal] = (
                    total / Decimal(count) if count > 0 else None
                )
            else:
                avg_v = None

            metric_aggregates[mid] = MetricAggregate(
                metric_id=mid,
                unit=metric_units.get(mid),
                count=count,
                min=min_v,
                max=max_v,
                avg=avg_v,
                last=last_v,
            )

        # 3. ヘルスファクターの集計
        hf_history = self._monitoring.get_health_factor_history(from_ts, to_ts)
        hf_values: List[Decimal] = [
            value for _, value in hf_history if value is not None
        ]

        if hf_values:
            min_hf = min(hf_values)
            max_hf = max(hf_values)
            last_hf = hf_values[-1]

            # HF のメトリクスも metric_aggregates に反映しておく
            total_hf = sum(hf_values, Decimal("0"))
            avg_hf: Optional[Decimal] = (
                total_hf / Decimal(len(hf_values)) if hf_values else None
            )
            metric_aggregates["aave_health_factor_current"] = MetricAggregate(
                metric_id="aave_health_factor_current",
                unit="ratio",
                count=len(hf_values),
                min=min_hf,
                max=max_hf,
                avg=avg_hf,
                last=last_hf,
            )
        else:
            min_hf = None
            max_hf = None
            last_hf = None

        # 4. 簡易ノート（人間向けの一言コメント）
        notes: Optional[str] = None
        if emergency_occurred:
            notes = "Emergency events occurred during this period."
        elif total_events == 0:
            notes = "No monitoring events recorded during this period."

        return AutomationReportSummary(
            period=period,
            from_timestamp=from_ts,
            to_timestamp=to_ts,
            total_events=total_events,
            info_count=level_counts.get(AlertLevel.INFO, 0),
            warning_count=level_counts.get(AlertLevel.WARNING, 0),
            alert_count=level_counts.get(AlertLevel.ALERT, 0),
            critical_count=level_counts.get(AlertLevel.CRITICAL, 0),
            emergency_count=level_counts.get(AlertLevel.EMERGENCY, 0),
            emergency_occurred=emergency_occurred,
            min_health_factor=min_hf,
            max_health_factor=max_hf,
            last_health_factor=last_hf,
            metric_aggregates=metric_aggregates,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # 通知連携向けヘルパー
    # ------------------------------------------------------------------
    @staticmethod
    def build_notification_message(
        summary: AutomationReportSummary,
        *,
        channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
    ) -> NotificationMessage:
        """
        レポートサマリから NotificationMessage を組み立てる。

        Phase5 時点では:
        - emergency_occurred=True の場合は EMERGENCY 通知
        - ALERT/WARNING が存在する場合は ALERT/WARNING レベル
        - イベント 0 件など正常系は INFO レベル

        実際の送信は NotificationService (CompositeNotificationService) 側で行う。
        """
        # severity 決定
        if summary.emergency_occurred or summary.emergency_count > 0:
            severity = NotificationSeverity.EMERGENCY
            status_label = "EMERGENCY"
        elif summary.alert_count > 0 or summary.critical_count > 0:
            severity = NotificationSeverity.ALERT
            status_label = "ALERT"
        elif summary.warning_count > 0:
            severity = NotificationSeverity.WARNING
            status_label = "WARNING"
        else:
            severity = NotificationSeverity.INFO
            status_label = "OK"

        # タイトル
        title = f"[AUTO-REPORT] {summary.period.value.upper()} summary ({status_label})"

        # 本文（シンプルなテキスト）
        period_str = (
            f"{summary.from_timestamp.isoformat()} - {summary.to_timestamp.isoformat()}"
        )
        lines: List[str] = [
            f"Period: {summary.period.value} ({period_str})",
            f"Events: total={summary.total_events}, "
            f"info={summary.info_count}, "
            f"warning={summary.warning_count}, "
            f"alert={summary.alert_count}, "
            f"critical={summary.critical_count}, "
            f"emergency={summary.emergency_count}",
        ]

        if summary.min_health_factor is not None or summary.last_health_factor is not None:
            lines.append(
                "Health factor: "
                f"min={summary.min_health_factor}, "
                f"max={summary.max_health_factor}, "
                f"last={summary.last_health_factor}"
            )

        if summary.notes:
            lines.append(f"Notes: {summary.notes}")

        body = "\n".join(lines)

        return NotificationMessage(
            channel=channel,
            severity=severity,
            title=title,
            body=body,
        )
