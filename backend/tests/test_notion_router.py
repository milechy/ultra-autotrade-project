# backend/tests/test_notion_router.py

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.notion.schemas import NotionNewsItem


def create_test_client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_notion_ingest_success():
    client = create_test_client()

    fake_items = [
        NotionNewsItem(
            id="page-1",
            url="https://example.com",
            summary="summary",
            sentiment="Positive",
            action="BUY",
            confidence=90.0,
            status="未処理",
            timestamp=None,
        )
    ]

    # NotionService.fetch_unprocessed_news をモックして成功ケースをシミュレート
    with patch(
        "app.notion.service.NotionService.fetch_unprocessed_news",
        return_value=fake_items,
    ):
        resp = client.post("/notion/ingest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == "page-1"


def test_notion_ingest_error():
    client = create_test_client()

    # NotionService.fetch_unprocessed_news が例外を投げた場合の 500 系レスポンスを確認
    with patch(
        "app.notion.service.NotionService.fetch_unprocessed_news",
        side_effect=Exception("unexpected error"),
    ):
        resp = client.post("/notion/ingest")

    assert resp.status_code >= 500

