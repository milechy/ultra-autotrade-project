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
    
def test_daily_report_contains_metric_aggregates_for_events() -> None:
    service = MonitoringService(
        latency_warning_threshold_s=10.0,
        latency_alert_threshold_s=30.0,
    )
    reporter = ReportingService(monitoring=service)

    base = _utc(2025, 1, 2, 12, 0)

    # 対象日内のイベント（レイテンシ2件 + 価格変動1件）
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=11),
        at=base - timedelta(hours=1),
    )
    service.record_latency(
        ComponentType.SYSTEM,
        timedelta(seconds=31),
        at=base - timedelta(minutes=10),
    )
    service.record_price_change_24h(
        percent_change=25.0,
        at=base - timedelta(minutes=5),
    )

    summary = reporter.generate_summary_report(ReportPeriod.DAILY, now=base)

    # latency_system_s の集計
    latency_agg = summary.metric_aggregates.get("latency_system_s")
    assert latency_agg is not None
    assert latency_agg.count == 2
    assert latency_agg.min == Decimal("11.0")
    assert latency_agg.max == Decimal("31.0")
    assert latency_agg.last == Decimal("31.0")
    assert latency_agg.avg == Decimal("21.0")

    # portfolio_value_change_1d_pct の集計
    price_agg = summary.metric_aggregates.get("portfolio_value_change_1d_pct")
    assert price_agg is not None
    assert price_agg.count == 1
    assert price_agg.min == Decimal("25.0")
    assert price_agg.max == Decimal("25.0")
    assert price_agg.last == Decimal("25.0")
    assert price_agg.avg == Decimal("25.0")


def test_daily_report_contains_metric_aggregate_for_health_factor() -> None:
    service = MonitoringService()
    reporter = ReportingService(monitoring=service)

    base = _utc(2025, 1, 2, 12, 0)

    # 同一日内のヘルスファクター履歴（3件）
    service.record_health_factor(
        Decimal("2.0"),
        at=base - timedelta(hours=6),
    )
    service.record_health_factor(
        Decimal("1.7"),
        at=base - timedelta(hours=3),
    )
    service.record_health_factor(
        Decimal("1.9"),
        at=base - timedelta(hours=1),
    )

    summary = reporter.generate_summary_report(ReportPeriod.DAILY, now=base)

    hf_agg = summary.metric_aggregates.get("aave_health_factor_current")
    assert hf_agg is not None
    assert hf_agg.count == 3
    assert hf_agg.min == Decimal("1.7")
    assert hf_agg.max == Decimal("2.0")
    assert hf_agg.last == Decimal("1.9")

    # AutomationReportSummary のヘルスファクター集計と整合していること
    assert summary.min_health_factor == hf_agg.min
    assert summary.max_health_factor == hf_agg.max
    assert summary.last_health_factor == hf_agg.last
