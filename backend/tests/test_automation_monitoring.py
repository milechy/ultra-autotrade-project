# backend/tests/test_automation_monitoring.py

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import AlertLevel, ComponentType


def test_latency_thresholds_warning_and_alert() -> None:
    service = MonitoringService(
        latency_warning_threshold_s=10.0,
        latency_alert_threshold_s=30.0,
    )

    # 11秒 → WARNING
    event_warning = service.record_latency(
        ComponentType.AI, timedelta(seconds=11), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert event_warning is not None
    assert event_warning.level == AlertLevel.WARNING
    assert event_warning.code == "LATENCY_WARNING"

    # 31秒 → ALERT
    event_alert = service.record_latency(
        ComponentType.AI, timedelta(seconds=31), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert event_alert is not None
    assert event_alert.level == AlertLevel.ALERT
    assert event_alert.code == "LATENCY_ALERT"


def test_health_factor_warning_and_emergency() -> None:
    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
    )

    # 1.7 → WARNING だが緊急停止にはならない
    status_warning = service.record_health_factor(
        Decimal("1.7"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert status_warning.level == AlertLevel.WARNING
    assert status_warning.is_emergency is False
    assert service.is_trading_allowed() is True

    # 1.5 → EMERGENCY で緊急停止
    status_emergency = service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert status_emergency.level == AlertLevel.EMERGENCY
    assert status_emergency.is_emergency is True
    assert service.is_trading_allowed() is False

    status = service.get_status()
    assert status.is_trading_paused is True
    assert status.last_health_factor == Decimal("1.5")
    assert status.emergency_reason is not None


def test_price_change_alert() -> None:
    service = MonitoringService(price_change_alert_threshold_pct=20.0)

    # 10% 変動 → イベントなし
    event_none = service.record_price_change_24h(
        percent_change=10.0,
        at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert event_none is None

    # 25% 変動 → ALERT
    event_alert = service.record_price_change_24h(
        percent_change=25.0,
        at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert event_alert is not None
    assert event_alert.level == AlertLevel.ALERT
    assert event_alert.code == "PRICE_CHANGE_ALERT"
