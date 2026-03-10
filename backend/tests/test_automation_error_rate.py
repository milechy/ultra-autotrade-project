# backend/tests/test_automation_error_rate.py
"""
AI API エラー率 > 20% のルールベース制御テスト。

docs/08_automation_rules.md: AI API エラー率 > 20% → アラート
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import AlertLevel, ComponentType


def test_single_error_no_alert() -> None:
    """1件のエラーはアラートにならない。"""
    service = MonitoringService(enable_state_sync=False)

    event = service.record_error(
        ComponentType.AI,
        at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    # 1/100 = 1% < 20% → アラートなし
    assert event is None


def test_error_rate_exceeds_threshold_emits_alert() -> None:
    """エラー率 > 20% でアラートイベントが発行される。"""
    service = MonitoringService(enable_state_sync=False)

    # 21回エラーを記録 → 21/100 = 21% > 20%
    event = None
    for i in range(21):
        event = service.record_error(
            ComponentType.AI,
            at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    assert event is not None
    assert event.level == AlertLevel.ALERT
    assert event.code == "ERROR_RATE_HIGH"
    assert "AI" in event.message or "ai" in event.message.lower()


def test_error_rate_exactly_at_threshold_no_alert() -> None:
    """エラー率 = 20% ちょうどはアラートにならない（> のみ）。"""
    service = MonitoringService(enable_state_sync=False)

    # 20回エラー → 20/100 = 20% → > でないのでアラートなし
    event = None
    for i in range(20):
        event = service.record_error(
            ComponentType.AI,
            at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    assert event is None


def test_different_components_tracked_independently() -> None:
    """コンポーネントごとに独立してエラー率を追跡する。"""
    service = MonitoringService(enable_state_sync=False)

    # AI コンポーネントに 21 回エラー → アラート
    ai_event = None
    for _ in range(21):
        ai_event = service.record_error(ComponentType.AI)

    # EXCHANGE コンポーネントは 1 回だけ → アラートなし
    exchange_event = service.record_error(ComponentType.EXCHANGE)

    assert ai_event is not None
    assert ai_event.level == AlertLevel.ALERT
    assert exchange_event is None


def test_error_rate_metric_attached_to_event() -> None:
    """アラートイベントにメトリクス情報が添付される。"""
    service = MonitoringService(enable_state_sync=False)

    event = None
    for _ in range(21):
        event = service.record_error(ComponentType.AI)

    assert event is not None
    assert event.metric is not None
    assert event.metric.unit == "ratio"
    assert event.metric.value > Decimal("0.20")
