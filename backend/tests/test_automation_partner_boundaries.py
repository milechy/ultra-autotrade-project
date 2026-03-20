# backend/tests/test_automation_partner_boundaries.py
"""
パートナー（viewer ロール）が見れる/見れないデータの境界テスト。

viewer: GET /api/automation/* は可能、POST /api/automation/workflow/run は不可
admin: 全操作可能
未認証: 全 endpoint で 401
"""

import os
import tempfile
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-partner-tests")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.api.automation_dashboard import get_monitoring_service, get_reporting_service
from app.automation.schemas import AutomationStatus, DashboardSnapshot, WorkflowRunResult
from app.database import Base, get_db
from app.main import create_app


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Generator:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine

    Base.metadata.drop_all(bind=test_engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db):
    override_get_db, _ = test_db
    os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    mock_monitoring = MagicMock()
    mock_monitoring.get_status.return_value = AutomationStatus.model_construct(
        is_trading_paused=False,
        emergency_reason=None,
        last_health_factor=None,
        last_price_change_24h=None,
        last_event_level="info",
        recent_events=[],
    )
    mock_monitoring.build_dashboard_snapshot.return_value = DashboardSnapshot.model_construct(
        generated_at=datetime.now(timezone.utc),
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        status=AutomationStatus.model_construct(
            is_trading_paused=False,
            emergency_reason=None,
            last_health_factor=None,
            last_price_change_24h=None,
            last_event_level="info",
            recent_events=[],
        ),
        metric_aggregates={},
    )

    mock_reporter = MagicMock()

    app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
    app.dependency_overrides[get_reporting_service] = lambda: mock_reporter
    return TestClient(app)


def _register_and_login(client: TestClient, email: str, username: str, password: str) -> str:
    """Register first user (admin) and return token."""
    client.post("/auth/register", json={"email": email, "username": username, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def _create_viewer_and_login(client: TestClient, admin_token: str) -> str:
    """Create a viewer user via admin and return viewer token."""
    client.post(
        "/users",
        json={
            "email": "viewer@test.com",
            "username": "viewer",
            "password": "viewerpass123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    r = client.post("/auth/login", json={"email": "viewer@test.com", "password": "viewerpass123"})
    return r.json()["access_token"]


class TestAutomationViewerAccess:
    """Viewer (partner) can read automation data but cannot trigger workflow."""

    def test_viewer_can_get_automation_status(self, client: TestClient):
        """Viewer は GET /api/automation/status にアクセスできる。"""
        admin_token = _register_and_login(client, "admin@example.com", "admin", "adminpassword123")
        viewer_token = _create_viewer_and_login(client, admin_token)

        response = client.get(
            "/api/automation/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200

    def test_viewer_can_get_dashboard(self, client: TestClient):
        """Viewer は GET /api/automation/dashboard にアクセスできる。"""
        admin_token = _register_and_login(client, "admin@example.com", "admin", "adminpassword123")
        viewer_token = _create_viewer_and_login(client, admin_token)

        response = client.get(
            "/api/automation/dashboard",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200

    def test_viewer_cannot_run_workflow(self, client: TestClient):
        """Viewer は POST /api/automation/workflow/run で 403 になる。"""
        admin_token = _register_and_login(client, "admin@example.com", "admin", "adminpassword123")
        viewer_token = _create_viewer_and_login(client, admin_token)

        response = client.post(
            "/api/automation/workflow/run",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_unauthenticated_cannot_access_status(self, client: TestClient):
        """未認証では GET /api/automation/status で 401 になる。"""
        response = client.get("/api/automation/status")
        assert response.status_code == 401

    def test_unauthenticated_cannot_access_dashboard(self, client: TestClient):
        """未認証では GET /api/automation/dashboard で 401 になる。"""
        response = client.get("/api/automation/dashboard")
        assert response.status_code == 401

    def test_unauthenticated_cannot_run_workflow(self, client: TestClient):
        """未認証では POST /api/automation/workflow/run で 401 になる。"""
        response = client.post("/api/automation/workflow/run")
        assert response.status_code == 401

    def test_admin_can_run_workflow(self, client: TestClient):
        """Admin は POST /api/automation/workflow/run を実行できる。"""
        admin_token = _register_and_login(client, "admin@example.com", "admin", "adminpassword123")

        with (
            patch("app.api.automation_dashboard.process_pending_knowledge") as mock_process,
            patch("app.api.automation_dashboard.KnowledgeService"),
            patch("app.api.automation_dashboard.AIService"),
            patch("app.api.automation_dashboard.get_exchange_service"),
        ):
            mock_process.return_value = WorkflowRunResult(status="no_items")
            response = client.post(
                "/api/automation/workflow/run",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert response.status_code == 200
