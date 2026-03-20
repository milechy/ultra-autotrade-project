# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_automation_emergency_stop_api.py

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin
from app.auth.models import UserRole
from app.automation.state import get_monitoring_service
from app.main import create_app


def _make_admin_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


def _make_client(override_auth: bool = True) -> tuple[TestClient, MagicMock]:
    mock_monitoring = MagicMock()
    app = create_app()
    app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
    if override_auth:
        app.dependency_overrides[require_admin] = lambda: _make_admin_user()
    return TestClient(app, raise_server_exceptions=False), mock_monitoring


def test_emergency_stop_returns_200_and_calls_service() -> None:
    """POST /automation/emergency-stop が 200 を返し activate_emergency_stop を呼ぶ。"""
    client, mock_monitoring = _make_client()

    resp = client.post("/automation/emergency-stop")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stopped"
    assert "緊急停止" in data["message"]
    mock_monitoring.activate_emergency_stop.assert_called_once()
    call_kwargs = mock_monitoring.activate_emergency_stop.call_args.kwargs
    assert "reason" in call_kwargs
    assert "user_id=1" in call_kwargs["reason"]


def test_emergency_stop_requires_admin() -> None:
    """POST /automation/emergency-stop は認証なしで 401/403 を返す。"""
    client, _ = _make_client(override_auth=False)

    resp = client.post("/automation/emergency-stop")

    assert resp.status_code in (401, 403)
