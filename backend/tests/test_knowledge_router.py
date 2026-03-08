# backend/tests/test_knowledge_router.py
"""Knowledge Hub router tests using FastAPI TestClient with dependency overrides."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_editor, require_viewer
from app.auth.models import UserRole
from app.knowledge.router import get_knowledge_service
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
    KnowledgeSearchResult,
)
from app.knowledge.service import KnowledgeServiceError
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


def _make_knowledge_item(
    id_: int = 1,
    status: KnowledgeItemStatus = KnowledgeItemStatus.PENDING,
    item_type: KnowledgeItemType = KnowledgeItemType.TEXT,
    title: str = "Test Item",
    raw_text: str = "Some content",
) -> KnowledgeItem:
    return KnowledgeItem(
        id=id_,
        source_url=None,
        title=title,
        raw_text=raw_text,
        status=status,
        chunk_count=2,
        item_type=item_type,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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
    app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


class TestCreateItemEndpoint:
    """POST /knowledge/items"""

    def test_create_item_text_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/items with text type returns 201 and item."""
        expected = _make_knowledge_item(id_=10)
        mock_service.create_item.return_value = expected

        response = client.post(
            "/knowledge/items",
            json={"item_type": "text", "raw_text": "Hello world", "title": "My doc"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 10
        assert data["status"] == "pending"
        mock_service.create_item.assert_called_once()

    def test_create_item_url_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/items with url type returns 201."""
        expected = _make_knowledge_item(id_=20, item_type=KnowledgeItemType.URL)
        mock_service.create_item.return_value = expected

        response = client.post(
            "/knowledge/items",
            json={"item_type": "url", "source_url": "https://example.com/page"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 20
        assert data["item_type"] == "url"

    def test_create_item_service_error_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /knowledge/items returns 422 when service raises KnowledgeServiceError."""
        mock_service.create_item.side_effect = KnowledgeServiceError("raw_text is required")

        response = client.post(
            "/knowledge/items",
            json={"item_type": "text"},
        )

        assert response.status_code == 422
        assert "raw_text is required" in response.json()["detail"]

    def test_create_item_unexpected_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /knowledge/items returns 500 on unexpected exception."""
        mock_service.create_item.side_effect = RuntimeError("database exploded")

        response = client.post(
            "/knowledge/items",
            json={"item_type": "text", "raw_text": "Some text"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestListItemsEndpoint:
    """GET /knowledge/items"""

    def test_list_items_returns_all(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /knowledge/items returns list of items."""
        items = [_make_knowledge_item(id_=1), _make_knowledge_item(id_=2)]
        mock_service.get_items.return_value = items

        response = client.get("/knowledge/items")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2

    def test_list_items_with_status_filter(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /knowledge/items?status=pending passes filter to service."""
        pending_item = _make_knowledge_item(id_=5, status=KnowledgeItemStatus.PENDING)
        mock_service.get_items.return_value = [pending_item]

        response = client.get("/knowledge/items?status=pending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"
        mock_service.get_items.assert_called_once()
        call_kwargs = mock_service.get_items.call_args
        assert call_kwargs is not None

    def test_list_items_empty(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /knowledge/items returns empty list when no items."""
        mock_service.get_items.return_value = []

        response = client.get("/knowledge/items")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_items_unexpected_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /knowledge/items returns 500 on unexpected exception."""
        mock_service.get_items.side_effect = RuntimeError("db down")

        response = client.get("/knowledge/items")

        assert response.status_code == 500


class TestSearchEndpoint:
    """POST /knowledge/search"""

    def test_search_returns_results(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/search returns results with count and query."""
        search_result = KnowledgeSearchResult(
            chunk_id=1,
            document_id=10,
            content="Bitcoin is a cryptocurrency",
            similarity=0.95,
            source_url="https://example.com",
            title="Crypto Guide",
        )
        mock_service.search.return_value = [search_result]

        response = client.post(
            "/knowledge/search",
            json={"query": "bitcoin price", "top_k": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["query"] == "bitcoin price"
        assert len(data["results"]) == 1
        assert data["results"][0]["similarity"] == pytest.approx(0.95)

    def test_search_empty_results(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /knowledge/search returns empty results list."""
        mock_service.search.return_value = []

        response = client.post(
            "/knowledge/search",
            json={"query": "obscure query"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_search_service_error_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /knowledge/search returns 422 when service raises KnowledgeServiceError."""
        mock_service.search.side_effect = KnowledgeServiceError("Failed to embed search query")

        response = client.post(
            "/knowledge/search",
            json={"query": "test query"},
        )

        assert response.status_code == 422
        assert "Failed to embed search query" in response.json()["detail"]

    def test_search_unexpected_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /knowledge/search returns 500 on unexpected exception."""
        mock_service.search.side_effect = RuntimeError("vector db crashed")

        response = client.post(
            "/knowledge/search",
            json={"query": "test query"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    def test_search_invalid_top_k_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /knowledge/search validates top_k range (1-20)."""
        response = client.post(
            "/knowledge/search",
            json={"query": "test", "top_k": 100},  # exceeds max of 20
        )

        assert response.status_code == 422


class TestUpdateStatusEndpoint:
    """PUT /knowledge/items/{item_id}/status"""

    def test_update_status_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """PUT /knowledge/items/{id}/status updates and returns item."""
        updated_item = _make_knowledge_item(id_=3, status=KnowledgeItemStatus.SKIPPED)
        mock_service.update_status.return_value = updated_item

        response = client.put(
            "/knowledge/items/3/status",
            params={"new_status": "skipped"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 3
        assert data["status"] == "skipped"
        mock_service.update_status.assert_called_once()

    def test_update_status_not_found_returns_404(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """PUT /knowledge/items/{id}/status returns 404 when item not found."""
        mock_service.update_status.side_effect = KnowledgeServiceError(
            "KnowledgeSource not found: id=9999"
        )

        response = client.put(
            "/knowledge/items/9999/status",
            params={"new_status": "skipped"},
        )

        assert response.status_code == 404
        assert "KnowledgeSource not found" in response.json()["detail"]

    def test_update_status_unexpected_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """PUT /knowledge/items/{id}/status returns 500 on unexpected exception."""
        mock_service.update_status.side_effect = RuntimeError("db connection lost")

        response = client.put(
            "/knowledge/items/1/status",
            params={"new_status": "analyzed"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    def test_update_status_to_analyzed(self, client: TestClient, mock_service: MagicMock) -> None:
        """PUT /knowledge/items/{id}/status can set status to analyzed."""
        updated_item = _make_knowledge_item(id_=8, status=KnowledgeItemStatus.ANALYZED)
        mock_service.update_status.return_value = updated_item

        response = client.put(
            "/knowledge/items/8/status",
            params={"new_status": "analyzed"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "analyzed"

    def test_update_status_to_error(self, client: TestClient, mock_service: MagicMock) -> None:
        """PUT /knowledge/items/{id}/status can set status to error."""
        updated_item = _make_knowledge_item(id_=9, status=KnowledgeItemStatus.ERROR)
        mock_service.update_status.return_value = updated_item

        response = client.put(
            "/knowledge/items/9/status",
            params={"new_status": "error"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"
