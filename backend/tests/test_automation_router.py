# backend/tests/test_automation_router.py
"""
automation_router.py のユニットテスト。

POST /automation/process-news のステータス判定をテスト。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.automation.automation_router import get_workflow_service
from app.automation.state import reset_state
from app.automation.workflow import WorkflowResult, WorkflowService
from app.main import app


@pytest.fixture(autouse=True)
def reset_monitoring_state() -> None:
    """各テスト前に MonitoringService の状態をリセット。"""
    reset_state()


@pytest.fixture
def client() -> TestClient:
    """テスト用 FastAPI クライアント。"""
    return TestClient(app)


def test_process_news_completed_status(client: TestClient) -> None:
    """全て成功時は completed ステータス。"""
    mock_result = WorkflowResult(
        fetched_count=2,
        analyzed_count=2,
        octobot_success_count=2,
        octobot_skipped_count=0,
        octobot_failed_count=0,
        notion_updated_count=2,
        errors=[],
    )

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.return_value = mock_result

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["octobot_failed_count"] == 0
        assert len(data["errors"]) == 0
    finally:
        app.dependency_overrides.clear()


def test_process_news_completed_with_errors_on_octobot_failure(
    client: TestClient,
) -> None:
    """OctoBot 送信失敗時は completed_with_errors ステータス。"""
    mock_result = WorkflowResult(
        fetched_count=2,
        analyzed_count=2,
        octobot_success_count=1,
        octobot_skipped_count=0,
        octobot_failed_count=1,  # 1件失敗
        notion_updated_count=2,
        errors=[],  # errors リストは空でも octobot_failed_count > 0 で判定
    )

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.return_value = mock_result

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_errors"
        assert data["octobot_failed_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_process_news_completed_with_errors_on_error_list(
    client: TestClient,
) -> None:
    """errors リストにエラーがある場合も completed_with_errors ステータス。"""
    mock_result = WorkflowResult(
        fetched_count=2,
        analyzed_count=2,
        octobot_success_count=2,
        octobot_skipped_count=0,
        octobot_failed_count=0,
        notion_updated_count=1,  # 1件は Notion 書き戻し失敗
        errors=["Failed to update Notion page page-001"],
    )

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.return_value = mock_result

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed_with_errors"
        assert len(data["errors"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_process_news_failed_status(client: TestClient) -> None:
    """全て失敗時は failed ステータス。"""
    mock_result = WorkflowResult(
        fetched_count=1,
        analyzed_count=0,  # AI 解析失敗
        octobot_success_count=0,
        octobot_skipped_count=0,
        octobot_failed_count=0,
        notion_updated_count=0,
        errors=["AI analysis failed: Connection error"],
    )

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.return_value = mock_result

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
    finally:
        app.dependency_overrides.clear()


def test_process_news_no_news_completed(client: TestClient) -> None:
    """未処理ニュースがない場合は completed ステータス。"""
    mock_result = WorkflowResult(
        fetched_count=0,
        analyzed_count=0,
        octobot_success_count=0,
        octobot_skipped_count=0,
        octobot_failed_count=0,
        notion_updated_count=0,
        errors=[],
    )

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.return_value = mock_result

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["fetched_count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_process_news_exception_sanitized_response(client: TestClient) -> None:
    """例外発生時、内部情報が漏れないことを確認。"""
    # 内部的な詳細情報を含む例外
    internal_error_message = "Database connection failed: host=192.168.1.100 user=admin password=secret123"

    mock_service = MagicMock(spec=WorkflowService)
    mock_service.process_pending_news.side_effect = Exception(internal_error_message)

    app.dependency_overrides[get_workflow_service] = lambda: mock_service

    try:
        response = client.post("/automation/process-news")

        # 500 エラーが返る
        assert response.status_code == 500

        data = response.json()

        # レスポンスには一般的なメッセージのみ
        assert data["detail"] == "Internal server error during news processing"

        # 内部情報が漏れていないことを確認
        assert "192.168.1.100" not in str(data)
        assert "password" not in str(data)
        assert "secret123" not in str(data)
        assert internal_error_message not in str(data)
    finally:
        app.dependency_overrides.clear()
