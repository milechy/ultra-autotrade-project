# backend/tests/test_automation_reports.py
"""Tests for app.api.automation_reports endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.automation_reports import get_reporting_service, router
from app.automation.schemas import (
    AutomationReportSummary,
    ReportPeriod,
)


def _make_report_summary() -> AutomationReportSummary:
    now = datetime.now(timezone.utc)
    return AutomationReportSummary(
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
        min_health_factor=None,
        max_health_factor=None,
        last_health_factor=None,
        metric_aggregates={},
    )


def _build_app(mock_service: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/automation/reports")
    app.dependency_overrides[get_reporting_service] = lambda: mock_service
    return app


class TestGetLatestReport:
    def test_returns_200_on_success(self):
        mock_service = MagicMock()
        mock_service.generate_latest_summary.return_value = _make_report_summary()

        app = _build_app(mock_service)
        client = TestClient(app)

        response = client.get("/automation/reports/latest")
        assert response.status_code == 200

    def test_calls_generate_latest_summary(self):
        mock_service = MagicMock()
        mock_service.generate_latest_summary.return_value = _make_report_summary()

        app = _build_app(mock_service)
        client = TestClient(app)

        client.get("/automation/reports/latest")
        mock_service.generate_latest_summary.assert_called_once()

    def test_response_body_contains_expected_fields(self):
        mock_service = MagicMock()
        mock_service.generate_latest_summary.return_value = _make_report_summary()

        app = _build_app(mock_service)
        client = TestClient(app)

        response = client.get("/automation/reports/latest")
        data = response.json()
        assert "period" in data
        assert "total_events" in data
        assert "emergency_occurred" in data

    def test_returns_500_when_service_raises(self):
        mock_service = MagicMock()
        mock_service.generate_latest_summary.side_effect = RuntimeError("DB unavailable")

        app = _build_app(mock_service)
        # TestClient raises by default; disable raise_server_exceptions to check 500
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/automation/reports/latest")
        assert response.status_code == 500

    def test_500_response_contains_detail(self):
        mock_service = MagicMock()
        mock_service.generate_latest_summary.side_effect = ValueError("bad state")

        app = _build_app(mock_service)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/automation/reports/latest")
        assert response.status_code == 500
        body = response.json()
        assert "detail" in body
