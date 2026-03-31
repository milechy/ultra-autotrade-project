# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_emergency_stop_dashboard.py
"""POST /api/automation/emergency-stop エンドポイントのテスト。"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.automation_dashboard import get_monitoring_service
from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import UserRole
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


class TestEmergencyStopDashboard:
    """POST /api/automation/emergency-stop テストクラス。"""

    def _make_client_with_mock_service(self) -> tuple[TestClient, MagicMock]:
        """テスト用 TestClient と MonitoringService モックを作成して返す。"""
        app = create_app()
        mock_monitoring = MagicMock()
        app.dependency_overrides[require_active_user] = lambda: _make_admin_user()
        app.dependency_overrides[require_admin] = lambda: _make_admin_user()
        app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
        client = TestClient(app)
        return client, mock_monitoring

    def test_emergency_stop_returns_stopped_status(self) -> None:
        """レスポンスが {"status": "stopped", ...} を返すこと。"""
        client, mock_monitoring = self._make_client_with_mock_service()
        response = client.post("/api/automation/emergency-stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert "message" in data

    def test_emergency_stop_calls_activate_emergency_stop(self) -> None:
        """MonitoringService.activate_emergency_stop が呼ばれること。"""
        client, mock_monitoring = self._make_client_with_mock_service()
        client.post("/api/automation/emergency-stop")

        mock_monitoring.activate_emergency_stop.assert_called_once()

    def test_emergency_stop_with_custom_reason(self) -> None:
        """カスタム reason が activate_emergency_stop に渡されること。"""
        client, mock_monitoring = self._make_client_with_mock_service()
        client.post(
            "/api/automation/emergency-stop",
            json={"reason": "Test emergency reason"},
        )

        mock_monitoring.activate_emergency_stop.assert_called_once()
        call_args = mock_monitoring.activate_emergency_stop.call_args
        reason_arg = call_args.kwargs.get("reason") or call_args.args[0]
        assert "Test emergency reason" in reason_arg

    def test_emergency_stop_reason_includes_user_id(self) -> None:
        """reason に user_id が含まれること。"""
        client, mock_monitoring = self._make_client_with_mock_service()
        client.post("/api/automation/emergency-stop")

        call_args = mock_monitoring.activate_emergency_stop.call_args
        reason_arg = call_args.kwargs.get("reason") or call_args.args[0]
        assert "user_id=1" in reason_arg
