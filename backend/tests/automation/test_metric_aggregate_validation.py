# backend/tests/automation/test_metric_aggregate_validation.py
"""MetricAggregate の Infinity/NaN バリデーターテスト。"""

from datetime import datetime
from decimal import Decimal

from app.automation.schemas import (
    AlertLevel,
    AutomationReportSummary,
    AutomationStatus,
    DashboardSnapshot,
    MetricAggregate,
    ReportPeriod,
)


def _make_aggregate(**kwargs: object) -> MetricAggregate:
    defaults = dict(metric_id="hf", count=1, min=None, max=None, avg=None, last=None)
    defaults.update(kwargs)
    return MetricAggregate(**defaults)  # type: ignore[arg-type]


def test_metric_aggregate_positive_infinity() -> None:
    agg = _make_aggregate(
        min=Decimal("Infinity"),
        max=Decimal("Infinity"),
        avg=Decimal("Infinity"),
        last=Decimal("Infinity"),
    )
    assert agg.min == Decimal("999.0")
    assert agg.max == Decimal("999.0")
    assert agg.avg == Decimal("999.0")
    assert agg.last == Decimal("999.0")


def test_metric_aggregate_negative_infinity() -> None:
    agg = _make_aggregate(
        min=Decimal("-Infinity"),
        max=Decimal("-Infinity"),
        avg=Decimal("-Infinity"),
        last=Decimal("-Infinity"),
    )
    assert agg.min == Decimal("-999.0")
    assert agg.max == Decimal("-999.0")
    assert agg.avg == Decimal("-999.0")
    assert agg.last == Decimal("-999.0")


def test_metric_aggregate_nan() -> None:
    agg = _make_aggregate(
        min=Decimal("NaN"),
        max=Decimal("NaN"),
        avg=Decimal("NaN"),
        last=Decimal("NaN"),
    )
    assert agg.min is None
    assert agg.max is None
    assert agg.avg is None
    assert agg.last is None


def test_metric_aggregate_normal_values() -> None:
    agg = _make_aggregate(
        min=Decimal("1.5"),
        max=Decimal("3.0"),
        avg=Decimal("2.0"),
        last=Decimal("2.5"),
    )
    assert agg.min == Decimal("1.5")
    assert agg.max == Decimal("3.0")
    assert agg.avg == Decimal("2.0")
    assert agg.last == Decimal("2.5")


def test_metric_aggregate_none_values() -> None:
    agg = _make_aggregate()
    assert agg.min is None
    assert agg.max is None
    assert agg.avg is None
    assert agg.last is None


def _make_automation_status() -> AutomationStatus:
    return AutomationStatus(
        is_trading_paused=False,
        last_event_level=AlertLevel.INFO,
    )


def test_dashboard_snapshot_with_infinity_metrics() -> None:
    now = datetime.utcnow()
    snap = DashboardSnapshot(
        generated_at=now,
        period_start=now,
        period_end=now,
        status=_make_automation_status(),
        metric_aggregates={
            "hf": {
                "metric_id": "hf",
                "count": 1,
                "min": Decimal("Infinity"),
                "max": Decimal("Infinity"),
                "avg": Decimal("Infinity"),
                "last": Decimal("Infinity"),
            }
        },
    )
    agg = snap.metric_aggregates["hf"]
    assert agg.min == Decimal("999.0")
    assert agg.max == Decimal("999.0")


def test_automation_report_summary_with_infinity_metrics() -> None:
    now = datetime.utcnow()
    summary = AutomationReportSummary(
        period=ReportPeriod.DAILY,
        from_timestamp=now,
        to_timestamp=now,
        total_events=0,
        info_count=0,
        warning_count=0,
        alert_count=0,
        critical_count=0,
        emergency_count=0,
        emergency_occurred=False,
        metric_aggregates={
            "hf": {
                "metric_id": "hf",
                "count": 1,
                "min": Decimal("Infinity"),
                "max": Decimal("-Infinity"),
                "avg": Decimal("NaN"),
                "last": Decimal("2.5"),
            }
        },
    )
    agg = summary.metric_aggregates["hf"]
    assert agg.min == Decimal("999.0")
    assert agg.max == Decimal("-999.0")
    assert agg.avg is None
    assert agg.last == Decimal("2.5")
