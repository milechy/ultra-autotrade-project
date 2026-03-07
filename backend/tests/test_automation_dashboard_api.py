from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, get_args, get_origin
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.automation_dashboard import get_monitoring_service, get_reporting_service
from app.auth.dependencies import require_viewer
from app.auth.models import UserRole
from app.automation.schemas import AutomationReportSummary, AutomationStatus, DashboardSnapshot
from app.main import create_app


def _make_admin_user() -> MagicMock:
    """テスト用 admin ユーザーを返す。"""
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


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
    """
    Pydantic v2 の model_construct を使って「必須フィールドだけ」埋めた最小モデルを作る。
    """
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
    def build_dashboard_snapshot(self, lookback: timedelta, now: datetime) -> DashboardSnapshot:  # noqa: ARG002
        # DashboardSnapshot の必須要素を満たす（契約を壊さない）
        return _minimal_model(
            DashboardSnapshot,
            overrides={
                "generated_at": now,
                "period_start": now,
                "period_end": now,
                "status": _minimal_model(
                    AutomationStatus,
                    overrides={
                        "is_trading_paused": False,
                        "emergency_reason": None,
                    },
                ),
                "metric_aggregates": {},  # dict を返す
            },
        )

    def get_status(self) -> AutomationStatus:
        return _minimal_model(
            AutomationStatus,
            overrides={
                "is_trading_paused": False,
                "emergency_reason": None,
            },
        )


class _StubReportingService:
    def generate_latest_summary(self) -> AutomationReportSummary:
        # latest を呼ぶ契約に合わせる（period 必須問題を回避）
        return _minimal_model(
            AutomationReportSummary,
            overrides={
                "metric_aggregates": {},
            },
        )


def _make_client() -> TestClient:
    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_monitoring_service] = lambda: _StubMonitoringService()
    app.dependency_overrides[get_reporting_service] = lambda: _StubReportingService()
    app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


client = _make_client()


def test_get_dashboard_snapshot_success():
    response = client.get("/api/automation/dashboard?lookback_hours=1")
    assert response.status_code == 200, response.text

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
    assert response.status_code == 200, response.text

    data = response.json()
    assert "is_trading_paused" in data
    assert "emergency_reason" in data


def test_get_latest_report():
    response = client.get("/api/automation/reports/latest")
    assert response.status_code == 200, response.text

    data = response.json()
    assert "metric_aggregates" in data
    assert isinstance(data["metric_aggregates"], dict)
