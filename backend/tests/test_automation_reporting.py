# backend/tests/test_automation_reporting.py

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.automation.monitoring_service import MonitoringService
from app.automation.reporting_service import ReportingService
from app.automation.schemas import ComponentType, ReportPeriod


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_daily_report_summarizes_events_and_health_factor() -> None:
    """
    DAILY レポートが:
    - 対象日のイベントだけを集計
    - レベルごとの件数
    - ヘルスファクターの min/max/last
    を正しく計算できることを確認。
    """
    service = MonitoringService()
    reporter = ReportingService(monitoring=service)

    base = _utc(2025, 1, 2, 12, 0)

    # 対象日内のイベント
    # 11秒 → WARNING
    service.record_latency(
        ComponentType.AI,
        timedelta(seconds=11),
        at=base - timedelta(hours=3),
    )
    # 31秒 → ALERT
    service.record_latency(
        ComponentType.AI,
        timedelta(seconds=31),
        at=base - timedelta(hours=2),
    )
    # HF 1.7 → WARNING
    service.record_health_factor(
        Decimal("1.7"),
        at=base - timedelta(hours=1, minutes=30),
    )
    # HF 1.5 → EMERGENCY
    service.record_health_factor(
        Decimal("1.5"),
        at=base - timedelta(hours=1),
    )

    # 対象日より前のイベント（集計対象外）
    service.record_latency(
        ComponentType.AI,
        timedelta(seconds=11),
        at=base - timedelta(days=2),
    )

    summary = reporter.generate_summary_report(ReportPeriod.DAILY, now=base)

    # 期間
    assert summary.period == ReportPeriod.DAILY
    assert summary.from_timestamp == _utc(2025, 1, 2, 0, 0)
    assert summary.to_timestamp == base

    # イベント件数（対象日の4件のみ）
    assert summary.total_events == 4
    assert summary.warning_count == 2  # latency(11s) + HF(1.7)
    assert summary.alert_count == 1    # latency(31s)
    assert summary.emergency_count == 1  # HF(1.5)
    assert summary.critical_count == 0
    assert summary.emergency_occurred is True

    # ヘルスファクター集計
    assert summary.min_health_factor == Decimal("1.5")
    assert summary.max_health_factor == Decimal("1.7")
    assert summary.last_health_factor == Decimal("1.5")


def test_weekly_report_uses_last_7_days_window() -> None:
    """
    WEEKLY レポートが「直近7日間」のイベントのみを集計対象とすることを確認。
    """
    service = MonitoringService()
    reporter = ReportingService(monitoring=service)

    base = _utc(2025, 1, 8, 12, 0)  # 水曜日想定

    # 6日前 → 集計対象（7日以内）
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=31),
        at=base - timedelta(days=6),
    )

    # 8日前 → 集計対象外
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=31),
        at=base - timedelta(days=8),
    )

    summary = reporter.generate_summary_report(ReportPeriod.WEEKLY, now=base)

    assert summary.period == ReportPeriod.WEEKLY
    # 直近7日分なので、件数は 1 のみ
    assert summary.total_events == 1
