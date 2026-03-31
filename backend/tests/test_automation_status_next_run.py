# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for next_scheduled_run field in GET /api/automation/status."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.automation.router import _compute_next_scheduled_run
from app.automation.router import router as automation_router
from app.automation.schemas import AutomationStatus
from app.automation.state import get_monitoring_service
from app.database import get_db


def _make_minimal_status() -> AutomationStatus:
    return AutomationStatus.model_construct(
        is_trading_paused=False,
        emergency_reason=None,
    )


def _build_test_app(mock_monitoring: MagicMock, db_session: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(automation_router, prefix="/api/automation")
    app.dependency_overrides[get_monitoring_service] = lambda: mock_monitoring
    app.dependency_overrides[get_db] = lambda: db_session
    return app


class TestNextScheduledRunField:
    """next_scheduled_run フィールドがレスポンスに含まれること。"""

    def test_status_includes_next_scheduled_run(self):
        """レスポンス JSON に next_scheduled_run キーが存在すること。"""
        mock_monitoring = MagicMock()
        mock_monitoring.get_status.return_value = _make_minimal_status()

        mock_db = MagicMock()
        # No decisions in DB → returns None
        mock_db.scalars.return_value.first.return_value = None

        app = _build_test_app(mock_monitoring, mock_db)
        client = TestClient(app)

        response = client.get("/api/automation/status")
        assert response.status_code == 200
        assert "next_scheduled_run" in response.json()

    def test_next_run_none_when_no_decisions(self):
        """AI判定履歴がない場合、next_scheduled_run は null を返すこと。"""
        mock_monitoring = MagicMock()
        mock_monitoring.get_status.return_value = _make_minimal_status()

        mock_db = MagicMock()
        mock_db.scalars.return_value.first.return_value = None

        app = _build_test_app(mock_monitoring, mock_db)
        client = TestClient(app)

        response = client.get("/api/automation/status")
        assert response.status_code == 200
        assert response.json()["next_scheduled_run"] is None


class TestComputeNextScheduledRun:
    """_compute_next_scheduled_run の単体テスト。"""

    def test_next_run_calculation(self):
        """last_decision + interval_hours = next_run の計算が正しいこと。"""
        last_decision_time = datetime(2026, 3, 31, 10, 0, 0, tzinfo=timezone.utc)
        mock_db = MagicMock()
        mock_db.scalars.return_value.first.return_value = last_decision_time

        with patch.dict("os.environ", {"AI_JUDGMENT_INTERVAL_HOURS": "4"}):
            result = _compute_next_scheduled_run(mock_db)

        expected = datetime(2026, 3, 31, 14, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_next_run_none_when_no_decisions(self):
        """判定履歴がない場合 None を返すこと。"""
        mock_db = MagicMock()
        mock_db.scalars.return_value.first.return_value = None

        result = _compute_next_scheduled_run(mock_db)
        assert result is None

    def test_next_run_past_returns_now(self):
        """算出された next_run が過去の場合、現在時刻以降の値を返すこと。"""
        # last_decision が 100 時間前 → next_run (4h後) は既に過去
        old_time = datetime.now(timezone.utc) - timedelta(hours=100)
        mock_db = MagicMock()
        mock_db.scalars.return_value.first.return_value = old_time

        before_call = datetime.now(timezone.utc)
        with patch.dict("os.environ", {"AI_JUDGMENT_INTERVAL_HOURS": "4"}):
            result = _compute_next_scheduled_run(mock_db)
        after_call = datetime.now(timezone.utc)

        assert result is not None
        assert before_call <= result <= after_call

    def test_next_run_naive_datetime_becomes_utc(self):
        """naive datetime (tzinfo=None) が渡された場合も UTC として扱われること。"""
        naive_time = datetime(2026, 3, 31, 10, 0, 0)  # no tzinfo
        mock_db = MagicMock()
        mock_db.scalars.return_value.first.return_value = naive_time

        with patch.dict("os.environ", {"AI_JUDGMENT_INTERVAL_HOURS": "4"}):
            result = _compute_next_scheduled_run(mock_db)

        assert result is not None
        assert result.tzinfo is not None
        expected = datetime(2026, 3, 31, 14, 0, 0, tzinfo=timezone.utc)
        assert result == expected
