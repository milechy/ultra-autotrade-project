# backend/tests/test_automation_emergency_report_service.py
from datetime import datetime, timezone
from decimal import Decimal

from app.automation.emergency_report_service import EmergencyReportService
from app.automation.schemas import (
    AlertLevel,
    AutomationReportSummary,
    ComponentType,
    MonitoringEvent,
    ReportPeriod,
)


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _base_summary(**overrides) -> AutomationReportSummary:
    base = {
        "period": ReportPeriod.DAILY,
        "from_timestamp": _utc(2025, 1, 1),
        "to_timestamp": _utc(2025, 1, 2),
        "total_events": 0,
        "info_count": 0,
        "warning_count": 0,
        "alert_count": 0,
        "critical_count": 0,
        "emergency_count": 0,
        "emergency_occurred": False,
        "min_health_factor": None,
        "max_health_factor": None,
        "last_health_factor": None,
        "notes": None,
    }
    base.update(overrides)
    return AutomationReportSummary(**base)


def _event(level: AlertLevel, code: str, message: str) -> MonitoringEvent:
    return MonitoringEvent(
        timestamp=_utc(2025, 1, 2, 12, 0),
        component=ComponentType.AAVE,
        level=level,
        code=code,
        message=message,
    )


def test_emergency_report_includes_severity_and_counts() -> None:
    summary = _base_summary(
        total_events=5,
        warning_count=1,
        alert_count=1,
        emergency_count=1,
        emergency_occurred=True,
        min_health_factor=Decimal("1.2"),
        max_health_factor=Decimal("1.8"),
        last_health_factor=Decimal("1.3"),
    )
    events = [
        _event(AlertLevel.EMERGENCY, "HF_BELOW_THRESHOLD", "Health factor dropped below safe threshold"),
    ]

    service = EmergencyReportService()
    report = service.build_emergency_report(summary, events)

    assert "[EMERGENCY]" in report.title
    assert "total=5" in report.body
    assert "emergency=1" in report.body
    assert "Health factor" in report.body
    assert "HF_BELOW_THRESHOLD" in report.body


def test_emergency_report_handles_no_events() -> None:
    summary = _base_summary(
        total_events=0,
        info_count=0,
        notes="No monitoring events recorded during this period.",
    )

    service = EmergencyReportService()
    report = service.build_emergency_report(summary, events=[])

    # INFO レベル相当のレポートになっていることをざっくり確認
    assert "INFO" in report.title or "OK" in report.title or "Automation" in report.title
    assert "No monitoring events" in report.body or "none" in report.body.lower()
    assert "Notes" in report.body
    assert "No monitoring events recorded during this period." in report.body
