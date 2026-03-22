# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_knowledge_router_search_test.py
"""Tests for GET /knowledge/search/test and POST /knowledge/workflow/trigger endpoints."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-password")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin, require_editor
from app.auth.models import UserRole
from app.automation.schemas import WorkflowRunResult
from app.knowledge.router import get_knowledge_service
from app.knowledge.schemas import KnowledgeSearchResult
from app.knowledge.service import KnowledgeServiceError
from app.main import create_app


def _make_admin_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


def _make_editor_user() -> MagicMock:
    user = MagicMock()
    user.id = 2
    user.email = "editor@example.com"
    user.username = "editor"
    user.role = UserRole.EDITOR.value
    user.is_active = True
    return user


def _make_search_result(
    chunk_id: int = 1,
    content: str = "BTC is bullish",
    similarity: float = 0.85,
    source_url: str = "https://example.com",
    title: str = "BTC Analysis",
) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        chunk_id=chunk_id,
        document_id=1,
        content=content,
        similarity=similarity,
        source_url=source_url,
        title=title,
    )


@pytest.fixture()
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def client(mock_service: MagicMock) -> TestClient:
    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_knowledge_service] = lambda: mock_service
    app.dependency_overrides[require_editor] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


class TestSearchTestEndpoint:
    """GET /knowledge/search/test"""

    def test_search_test_returns_results(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /knowledge/search/test returns 200 with formatted results."""
        mock_service.search.return_value = [
            _make_search_result(chunk_id=1, content="BTC bullish trend", similarity=0.85),
            _make_search_result(chunk_id=2, content="ETH support level", similarity=0.72),
        ]

        response = client.get("/knowledge/search/test?query=crypto+trend&top_k=5")

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "crypto trend"
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["similarity_score"] == 0.85
        assert data["results"][0]["content"] == "BTC bullish trend"

    def test_search_test_empty_results(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /knowledge/search/test returns 200 with empty list when no matches."""
        mock_service.search.return_value = []

        response = client.get("/knowledge/search/test?query=nonexistent+query")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_search_test_missing_query_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /knowledge/search/test without query param returns 422."""
        response = client.get("/knowledge/search/test")

        assert response.status_code == 422

    def test_search_test_service_error_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /knowledge/search/test returns 422 when KnowledgeServiceError raised."""
        mock_service.search.side_effect = KnowledgeServiceError("embedding failed")

        response = client.get("/knowledge/search/test?query=test+query")

        assert response.status_code == 422
        assert "embedding failed" in response.json()["detail"]

    def test_search_test_source_mapping(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /knowledge/search/test maps source_url to source field."""
        mock_service.search.return_value = [
            _make_search_result(source_url="https://example.com/btc", title="BTC Report"),
        ]

        response = client.get("/knowledge/search/test?query=btc")

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["source"] == "https://example.com/btc"


class TestWorkflowTriggerEndpoint:
    """POST /knowledge/workflow/trigger"""

    def test_workflow_trigger_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/workflow/trigger returns 200 with WorkflowRunResult."""
        expected = WorkflowRunResult(
            status="completed",
            fetched_count=3,
            traded_count=1,
            skipped_count=2,
        )

        with patch("app.automation.workflow.process_pending_knowledge", return_value=expected):
            response = client.post("/knowledge/workflow/trigger")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["fetched_count"] == 3

    def test_workflow_trigger_no_items(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/workflow/trigger returns no_items when nothing pending."""
        expected = WorkflowRunResult(status="no_items")

        with patch("app.automation.workflow.process_pending_knowledge", return_value=expected):
            response = client.post("/knowledge/workflow/trigger")

        assert response.status_code == 200
        assert response.json()["status"] == "no_items"

    def test_workflow_trigger_requires_admin(self, mock_service: MagicMock) -> None:
        """POST /knowledge/workflow/trigger returns 403 for non-admin user."""
        editor_user = _make_editor_user()
        app = create_app()
        app.dependency_overrides[get_knowledge_service] = lambda: mock_service
        # Only override require_editor, NOT require_admin → 403 for admin route
        app.dependency_overrides[require_editor] = lambda: editor_user
        non_admin_client = TestClient(app)

        response = non_admin_client.post(
            "/knowledge/workflow/trigger",
            headers={"Authorization": "Bearer fake-editor-token"},
        )

        # Without admin override, should fail auth (401 or 403)
        assert response.status_code in (401, 403)
