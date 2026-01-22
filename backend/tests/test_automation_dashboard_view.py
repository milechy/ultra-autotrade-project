# backend/tests/test_automation_dashboard_view.py

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import ComponentType


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_dashboard_snapshot_aggregates_metrics_within_lookback_window() -> None:
    service = MonitoringService(
        latency_warning_threshold_s=10.0,
        latency_alert_threshold_s=30.0,
    )

    base = _utc(2025, 1, 2, 12, 0)

    # lookback 内（1時間）のイベント: 2件
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=11),
        at=base - timedelta(minutes=30),
    )
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=31),
        at=base - timedelta(minutes=10),
    )

    # lookback 外（2時間前）のイベント: 集計対象外
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=40),
        at=base - timedelta(hours=2),
    )

    snapshot = service.build_dashboard_snapshot(
        lookback=timedelta(hours=1),
        now=base,
    )

    # SYSTEM 向けレイテンシメトリクスが 2件だけ集計されていること
    agg = snapshot.metric_aggregates.get("latency_system_s")
    assert agg is not None
    assert agg.count == 2
    assert agg.min == Decimal("11.0")
    assert agg.max == Decimal("31.0")
    assert agg.last == Decimal("31.0")
    # 平均値も確認
    assert agg.avg == Decimal("21.0")


def test_dashboard_snapshot_empty_when_no_events_in_lookback() -> None:
    service = MonitoringService()
    base = _utc(2025, 1, 2, 12, 0)

    # 過去にイベントがあっても、lookback より前なら集計対象外
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=31),
        at=base - timedelta(hours=2),
    )

    snapshot = service.build_dashboard_snapshot(
        lookback=timedelta(hours=1),
        now=base,
    )

    # メトリクス集計は空だが、ステータス自体は取得できること
    assert snapshot.metric_aggregates == {}
    assert snapshot.status.is_trading_paused is False
    assert snapshot.period_end == base
    assert snapshot.period_start == base - timedelta(hours=1)
