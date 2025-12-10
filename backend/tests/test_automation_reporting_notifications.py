# backend/tests/test_automation_reporting_notifications.py

from datetime import datetime, timezone
from decimal import Decimal

from app.automation.reporting_service import ReportingService
from app.automation.schemas import AutomationReportSummary, ReportPeriod
from app.notifications.schemas import NotificationChannel, NotificationSeverity
from app.automation.monitoring_service import MonitoringService


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _base_summary(**overrides) -> AutomationReportSummary:
    base = dict(
        period=ReportPeriod.DAILY,
        from_timestamp=_utc(2025, 1, 1),
        to_timestamp=_utc(2025, 1, 2),
        total_events=0,
        info_count=0,
        warning_count=0,
        alert_count=0,
        critical_count=0,
        emergency_count=0,
        emergency_occurred=False,
        min_health_factor=None,
        max_health_factor=None,
        last_health_factor=None,
        notes=None,
    )
    base.update(overrides)
    return AutomationReportSummary(**base)


def test_build_notification_message_emergency() -> None:
    """
    emergency_occurred=True の場合、EMERGENCY レベルの通知が生成されること。
    """
    monitoring = MonitoringService()
    reporter = ReportingService(monitoring=monitoring)

    summary = _base_summary(
        total_events=3,
        emergency_count=1,
        emergency_occurred=True,
    )

    msg = reporter.build_notification_message(
        summary,
        channel=NotificationChannel.INTERNAL_LOG,
    )

    assert msg.severity == NotificationSeverity.EMERGENCY
    assert "EMERGENCY" in msg.title
    assert "emergency=1" in msg.body or "emergency=1" in msg.body.replace(" ", "")


def test_build_notification_message_ok() -> None:
    """
    イベントがなく正常な期間の場合、INFO レベルの通知が生成されること。
    """
    monitoring = MonitoringService()
    reporter = ReportingService(monitoring=monitoring)

    summary = _base_summary(
        total_events=0,
        info_count=0,
        notes="No monitoring events recorded during this period.",
    )

    msg = reporter.build_notification_message(
        summary,
        channel=NotificationChannel.INTERNAL_LOG,
    )

    assert msg.severity == NotificationSeverity.INFO
    assert "OK" in msg.title
    assert "No monitoring events" in msg.body
