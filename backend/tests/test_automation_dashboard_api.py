# backend/tests/test_automation_dashboard_api.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, get_args, get_origin

from fastapi.testclient import TestClient

from app.main import create_app
from app.api.automation_dashboard import get_monitoring_service, get_reporting_service
from app.automation.schemas import AutomationReportSummary, AutomationStatus, DashboardSnapshot


def _placeholder_for_type(tp: Any) -> Any:
    origin = get_origin(tp)
    args = get_args(tp)

    # Optional / Union
    if origin is not None and "Union" in str(origin):
        if type(None) in args:
            return None
        return _placeholder_for_type(args[0]) if args else None

    if origin is list:
        return []
    if origin is dict:
        return {}
    if origin is tuple:
        return tuple()

    if tp is datetime:
        return datetime.now(timezone.utc)
    if tp is bool:
        return False
    if tp is int:
        return 0
    if tp is float:
        return 0.0
    if tp is str:
        return ""

    if hasattr(tp, "model_construct"):
        return tp.model_construct()

    return None


def _minimal_model(Model: Any, overrides: dict[str, Any] | None = None) -> Any:
    overrides = overrides or {}
    values: dict[str, Any] = {}

    for name, field in getattr(Model, "model_fields", {}).items():
        if name in overrides:
            continue
        is_required = getattr(field, "is_required", lambda: False)()
        if is_required:
            values[name] = _placeholder_for_type(field.annotation)

    return Model.model_construct(**values, **overrides)


class _StubMonitoringService:
    def build_dashboard_snapshot(self, lookback: int, now: datetime) -> DashboardSnapshot:  # noqa: ARG002
        # warningより、metric_aggregates は dict を期待している可能性が高い
        return _minimal_model(
            DashboardSnapshot,
            overrides={
                "period_start": now,
                "period_end": now,
                "metric_aggregates": {},  # dict で返す
            },
        )

    def get_status(self) -> AutomationStatus:
        return _minimal_model(
            AutomationStatus,
            overrides={
                "is_trading_paused": False,
                # enumの可能性があるため値は固定しない（存在確認で見る）
                "emergency_reason": None,
            },
        )


class _StubReportingService:
    def generate_summary_report(self) -> AutomationReportSummary:
        # generated_at が無いスキーマのため、ここでは metric_aggregates を確実に入れる
        return _minimal_model(
            AutomationReportSummary,
            overrides={
                "metric_aggregates": {},  # dict で返す
            },
        )


app = create_app()
app.dependency_overrides[get_monitoring_service] = lambda: _StubMonitoringService()
app.dependency_overrides[get_reporting_service] = lambda: _StubReportingService()

client = TestClient(app)


def test_get_dashboard_snapshot_success():
    response = client.get("/api/automation/dashboard?lookback_hours=1")
    assert response.status_code == 200

    data = response.json()
    assert "period_start" in data
    assert "period_end" in data
    assert "metric_aggregates" in data
    assert isinstance(data["metric_aggregates"], dict)


def test_get_dashboard_snapshot_invalid_lookback():
    response = client.get("/api/automation/dashboard?lookback_hours=0")
    assert response.status_code == 422


def test_get_automation_status():
    response = client.get("/api/automation/status")
    assert response.status_code == 200

    data = response.json()
    assert "is_trading_paused" in data
    # last_event_level がある場合のみ存在確認（enum/型差で落とさない）
    # emergency_reason は runbook 的にも重要なので存在確認
    assert "emergency_reason" in data


def test_get_latest_report():
    response = client.get("/api/automation/reports/latest")
    assert response.status_code == 200

    data = response.json()
    # Phase10 前提のキー
    assert "metric_aggregates" in data
    assert isinstance(data["metric_aggregates"], dict)
