# backend/tests/test_ai_router.py

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.schemas import AIAnalysisResult, TradeAction
from app.main import create_app


def create_test_client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_ai_analyze_success():
    client = create_test_client()

    dummy_result = AIAnalysisResult(
        id="page-1",
        url="https://example.com/news1",
        action=TradeAction.BUY,
        confidence=80,
        sentiment="positive",
        summary="summary",
        reason="reason",
        timestamp=datetime.now(timezone.utc),
    )

    # AIService.analyze_items をモックして、期待する結果を返すようにする
    with patch(
        "app.ai.service.AIService.analyze_items",
        return_value=[dummy_result],
    ):
        payload = {
            "items": [
                {
                    "id": "page-1",
                    "url": "https://example.com/news1",
                    "summary": "positive news",
                    "sentiment": None,
                    "action": None,
                    "confidence": None,
                    "status": "未処理",
                    "timestamp": None,
                }
            ]
        }
        resp = client.post("/ai/analyze", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["results"][0]["action"] == TradeAction.BUY.value


def test_ai_analyze_unexpected_error():
    client = create_test_client()

    # analyze_items が例外を投げた場合に 500 系を返すことを確認
    with patch(
        "app.ai.service.AIService.analyze_items",
        side_effect=Exception("unexpected error"),
    ):
        payload = {"items": []}
        resp = client.post("/ai/analyze", json=payload)

    assert resp.status_code >= 500

