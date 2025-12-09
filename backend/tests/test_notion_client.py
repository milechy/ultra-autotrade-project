# backend/tests/test_notion_client.py

import json
from unittest.mock import patch

import httpx
import pytest

from app.notion.client import NotionClient, NotionClientError, NotionAuthError
from app.notion.config import get_notion_config

@pytest.fixture(autouse=True)
def _notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "dummy-key")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dummy-db")


def test_query_unprocessed_entries_success(monkeypatch):
    client = NotionClient()

    fake_response_data = {
        "results": [
            {
                "id": "page-1",
                "properties": {
                    "URL": {"url": "https://example.com"},
                    "Status": {"select": {"name": "未処理"}},
                },
            }
        ]
    }

    def fake_post(*args, **kwargs):
        return httpx.Response(
            status_code=200,
            content=json.dumps(fake_response_data).encode("utf-8"),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    results = client.query_unprocessed_entries()

    assert len(results) == 1
    assert results[0]["id"] == "page-1"


def test_query_unprocessed_entries_401(monkeypatch):
    client = NotionClient()

    def fake_post(*args, **kwargs):
        return httpx.Response(status_code=401, content=b"")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(NotionAuthError):
        client.query_unprocessed_entries()


def test_query_unprocessed_entries_network_error(monkeypatch):
    client = NotionClient()

    def fake_post(*args, **kwargs):
        raise httpx.RequestError("network error", request=None)

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(NotionClientError):
        client.query_unprocessed_entries()

