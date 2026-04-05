# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for app.automation.router endpoints."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.automation.router import router as automation_router
from app.automation.schemas import (
    AutomationReportSummary,
    AutomationStatus,
    DashboardSnapshot,
    WorkflowRunResult,
)
from app.automation.state import get_monitoring_service
from app.database import get_db


def _make_minimal_automation_status() -> AutomationStatus:
    return AutomationStatus.model_construct(
        is_trading_paused=False,
        emergency_reason=None,
    )


def _make_minimal_dashboard_snapshot() -> DashboardSnapshot:
    from datetime import datetime, timezone

    return DashboardSnapshot.model_construct(
        generated_at=datetime.now(timezone.utc),
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        status=_make_minimal_automation_status(),
        metric_aggregates={},
    )


def _make_minimal_report_summary() -> AutomationReportSummary:
    return AutomationReportSummary.model_construct(
        metric_aggregates={},
    )


def _build_test_app(
    mock_monitoring: MagicMock | None = None,
    db_session: MagicMock | None = None,
) -> FastAPI:
    """Build a minimal test FastAPI app with the automation router mounted."""
    app = FastAPI()
    app.include_router(automation_router, prefix="/api/automation")

    if mock_monitoring is not None:
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

    if db_session is not None:
        app.dependency_overrides[get_db] = lambda: db_session

    return app


def _make_mock_db() -> MagicMock:
    """_compute_next_scheduled_run が None を返すよう db をモックする。"""
    mock_db = MagicMock()
    mock_db.scalars.return_value.first.return_value = None
    return mock_db


class TestGetAutomationStatus:
    """GET /api/automation/status"""

    def test_returns_200_with_status(self):
        mock_monitoring = MagicMock()
        mock_monitoring.get_status.return_value = _make_minimal_automation_status()

        app = _build_test_app(mock_monitoring=mock_monitoring, db_session=_make_mock_db())
        client = TestClient(app)

        response = client.get("/api/automation/status")
        assert response.status_code == 200
        mock_monitoring.get_status.assert_called_once()

    def test_response_contains_is_trading_paused(self):
        mock_monitoring = MagicMock()
        mock_monitoring.get_status.return_value = AutomationStatus.model_construct(
            is_trading_paused=True,
            emergency_reason="Test emergency",
        )

        app = _build_test_app(mock_monitoring=mock_monitoring, db_session=_make_mock_db())
        client = TestClient(app)

        response = client.get("/api/automation/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_trading_paused" in data


class TestGetDashboardSnapshot:
    """GET /api/automation/dashboard"""

    def test_returns_200_with_default_lookback(self):
        mock_monitoring = MagicMock()
        mock_monitoring.build_dashboard_snapshot.return_value = _make_minimal_dashboard_snapshot()

        app = _build_test_app(mock_monitoring=mock_monitoring)
        client = TestClient(app)

        response = client.get("/api/automation/dashboard")
        assert response.status_code == 200
        mock_monitoring.build_dashboard_snapshot.assert_called_once()

    def test_passes_lookback_hours_to_service(self):
        mock_monitoring = MagicMock()
        mock_monitoring.build_dashboard_snapshot.return_value = _make_minimal_dashboard_snapshot()

        app = _build_test_app(mock_monitoring=mock_monitoring)
        client = TestClient(app)

        response = client.get("/api/automation/dashboard?lookback_hours=3")
        assert response.status_code == 200

        call_kwargs = mock_monitoring.build_dashboard_snapshot.call_args
        assert call_kwargs.kwargs["lookback"] == timedelta(hours=3)

    def test_returns_422_for_lookback_below_minimum(self):
        mock_monitoring = MagicMock()
        app = _build_test_app(mock_monitoring=mock_monitoring)
        client = TestClient(app)

        response = client.get("/api/automation/dashboard?lookback_hours=0")
        assert response.status_code == 422

    def test_returns_422_for_lookback_above_maximum(self):
        mock_monitoring = MagicMock()
        app = _build_test_app(mock_monitoring=mock_monitoring)
        client = TestClient(app)

        response = client.get("/api/automation/dashboard?lookback_hours=25")
        assert response.status_code == 422


class TestGetLatestReport:
    """GET /api/automation/reports/latest"""

    def _make_app_with_reporting_stub(self, report_summary=None):
        from app.automation.router import get_reporting_service

        if report_summary is None:
            report_summary = _make_minimal_report_summary()

        mock_reporter = MagicMock()
        mock_reporter.generate_summary_report.return_value = report_summary

        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        app.dependency_overrides[get_reporting_service] = lambda: mock_reporter

        return app, mock_reporter

    def test_returns_200_with_default_period(self):
        from app.automation.router import get_reporting_service
        from app.automation.schemas import ReportPeriod

        mock_reporter = MagicMock()
        mock_reporter.generate_summary_report.return_value = _make_minimal_report_summary()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        app.dependency_overrides[get_reporting_service] = lambda: mock_reporter

        client = TestClient(app)
        response = client.get("/api/automation/reports/latest")

        assert response.status_code == 200
        mock_reporter.generate_summary_report.assert_called_once_with(period=ReportPeriod.DAILY)

    def test_returns_200_with_weekly_period(self):
        from app.automation.router import get_reporting_service
        from app.automation.schemas import ReportPeriod

        mock_reporter = MagicMock()
        mock_reporter.generate_summary_report.return_value = _make_minimal_report_summary()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        app.dependency_overrides[get_reporting_service] = lambda: mock_reporter

        client = TestClient(app)
        # ReportPeriod enum values are lowercase: "weekly", "daily"
        response = client.get("/api/automation/reports/latest?period=weekly")

        assert response.status_code == 200
        mock_reporter.generate_summary_report.assert_called_once_with(period=ReportPeriod.WEEKLY)

    def test_returns_200_with_daily_period(self):
        from app.automation.router import get_reporting_service
        from app.automation.schemas import ReportPeriod

        mock_reporter = MagicMock()
        mock_reporter.generate_summary_report.return_value = _make_minimal_report_summary()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        app.dependency_overrides[get_reporting_service] = lambda: mock_reporter

        client = TestClient(app)
        # ReportPeriod enum values are lowercase: "weekly", "daily"
        response = client.get("/api/automation/reports/latest?period=daily")

        assert response.status_code == 200
        mock_reporter.generate_summary_report.assert_called_once_with(period=ReportPeriod.DAILY)


class TestWorkflowRun:
    """POST /api/automation/workflow/run"""

    def _make_app_with_workflow_mock(self, process_return_value=None):
        """Create a test app with process_pending_knowledge mocked."""
        if process_return_value is None:
            process_return_value = WorkflowRunResult(status="no_items")

        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        app.dependency_overrides[get_db] = lambda: mock_db

        return app

    def test_workflow_run_dry_run_returns_no_items(self):
        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

        with (
            patch("app.automation.router.KnowledgeService") as _MockKS,
            patch("app.automation.router.AIService") as _MockAI,
            patch("app.automation.router.get_exchange_service") as _mock_get_ex,
            patch("app.automation.router.process_pending_knowledge") as mock_process,
        ):
            mock_process.return_value = WorkflowRunResult(status="no_items")
            client = TestClient(app)
            response = client.post("/api/automation/workflow/run?dry_run=true")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_items"
        assert data["fetched_count"] == 0
        assert data["traded_count"] == 0
        assert data["errors"] == []

    def test_workflow_run_default_dry_run_is_true(self):
        """dry_run defaults to True when not specified."""
        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

        with (
            patch("app.automation.router.KnowledgeService"),
            patch("app.automation.router.AIService"),
            patch("app.automation.router.get_exchange_service"),
            patch("app.automation.router.process_pending_knowledge") as mock_process,
        ):
            mock_process.return_value = WorkflowRunResult(status="no_items")
            client = TestClient(app)
            response = client.post("/api/automation/workflow/run")

        assert response.status_code == 200
        # Verify dry_run=True was passed
        call_kwargs = mock_process.call_args
        assert call_kwargs.kwargs.get("dry_run") is True

    def test_workflow_run_with_completed_result(self):
        """When workflow returns a completed result with trades."""
        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        fake_result = WorkflowRunResult(
            fetched_count=1,
            analyzed_count=1,
            traded_count=0,
            hold_count=1,
            skipped_count=0,
            errors=[],
            status="completed",
        )

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

        with (
            patch("app.automation.router.KnowledgeService"),
            patch("app.automation.router.AIService"),
            patch("app.automation.router.get_exchange_service"),
            patch("app.automation.router.process_pending_knowledge") as mock_process,
        ):
            mock_process.return_value = fake_result
            client = TestClient(app)
            response = client.post("/api/automation/workflow/run?dry_run=true")

        assert response.status_code == 200
        data = response.json()
        assert data["fetched_count"] == 1
        assert data["hold_count"] == 1
        assert data["traded_count"] == 0
        assert data["status"] == "completed"

    def test_workflow_run_with_successful_trade(self):
        """When workflow returns results with a successful order."""
        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        fake_result = WorkflowRunResult(
            fetched_count=1,
            analyzed_count=1,
            traded_count=1,
            hold_count=0,
            skipped_count=0,
            errors=[],
            status="completed",
        )

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

        with (
            patch("app.automation.router.KnowledgeService"),
            patch("app.automation.router.AIService"),
            patch("app.automation.router.get_exchange_service"),
            patch("app.automation.router.process_pending_knowledge") as mock_process,
        ):
            mock_process.return_value = fake_result
            client = TestClient(app)
            response = client.post("/api/automation/workflow/run?dry_run=false")

        assert response.status_code == 200
        data = response.json()
        assert data["fetched_count"] == 1
        assert data["traded_count"] == 1
        assert data["status"] == "completed"

    def test_workflow_run_dry_run_false_passes_flag(self):
        """dry_run=false is correctly passed to process_pending_knowledge."""
        mock_db = MagicMock()
        mock_monitoring = MagicMock()

        app = FastAPI()
        app.include_router(automation_router, prefix="/api/automation")
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring

        with (
            patch("app.automation.router.KnowledgeService"),
            patch("app.automation.router.AIService"),
            patch("app.automation.router.get_exchange_service"),
            patch("app.automation.router.process_pending_knowledge") as mock_process,
        ):
            mock_process.return_value = WorkflowRunResult(status="no_items")
            client = TestClient(app)
            client.post("/api/automation/workflow/run?dry_run=false")

        call_kwargs = mock_process.call_args
        assert call_kwargs.kwargs.get("dry_run") is False
