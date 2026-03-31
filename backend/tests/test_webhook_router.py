# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_webhook_router.py

"""
Webhook router のユニットテスト。

全テストはモックを使用し、外部 DB / API 通信を行わない。
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.knowledge.router import get_knowledge_service
from app.main import create_app


def _make_mock_item(item_id: int = 42) -> MagicMock:
    """KnowledgeItem に似せた MagicMock を返すヘルパー。"""
    mock_item = MagicMock()
    mock_item.id = item_id
    return mock_item


@pytest.fixture()
def mock_service() -> MagicMock:
    """KnowledgeService の MagicMock。"""
    service = MagicMock()
    service.create_item.return_value = _make_mock_item(42)
    return service


@pytest.fixture()
def mock_db() -> MagicMock:
    """DB Session の MagicMock。"""
    return MagicMock()


@pytest.fixture()
def client(mock_service: MagicMock, mock_db: MagicMock) -> TestClient:
    """依存性を差し替えた TestClient を返すフィクスチャ。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_knowledge_service] = lambda: mock_service
    return TestClient(app)


class TestTradingViewWebhook:
    """POST /webhook/tradingview"""

    def test_tradingview_webhook_registers_knowledge(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """TradingView ペイロードを送信すると 200 が返り、knowledge_item_id が設定されること。"""
        response = client.post(
            "/webhook/tradingview",
            json={
                "ticker": "BTCUSDT",
                "action": "buy",
                "price": 100000.5,
                "message": "breakout",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["knowledge_item_id"] == 42
        mock_service.create_item.assert_called_once()

    def test_tradingview_payload_text_format(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """ticker / action / price / message が raw_text に含まれること。"""
        response = client.post(
            "/webhook/tradingview",
            json={
                "ticker": "BTCUSDT",
                "action": "buy",
                "price": 100000.5,
                "message": "breakout",
            },
        )

        assert response.status_code == 200
        mock_service.create_item.assert_called_once()

        call_args = mock_service.create_item.call_args
        request = call_args[0][1]  # 第2引数が KnowledgeCreateRequest
        raw_text = request.raw_text

        assert raw_text is not None
        assert "BTCUSDT" in raw_text
        assert "buy" in raw_text
        assert "100000.5" in raw_text
        assert "breakout" in raw_text

    def test_tradingview_webhook_handles_service_error(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """service.create_item が例外を送出しても 200 を返し、knowledge_item_id が None であること。"""
        mock_service.create_item.side_effect = Exception("DB error")

        response = client.post(
            "/webhook/tradingview",
            json={"ticker": "ETHUSDT", "action": "sell"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["knowledge_item_id"] is None
        assert "Registration failed" in data["message"]


class TestGenericWebhook:
    """POST /webhook/generic"""

    def test_generic_webhook_registers_knowledge(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """汎用ペイロードを送信すると 200 が返り、create_item が呼ばれること。"""
        response = client.post(
            "/webhook/generic",
            json={"content": "some text"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["knowledge_item_id"] == 42
        mock_service.create_item.assert_called_once()

    def test_generic_webhook_with_url_uses_url_type(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """url が指定されている場合は URL 種別で登録されること。"""
        response = client.post(
            "/webhook/generic",
            json={
                "content": "See article",
                "url": "https://example.com/article",
                "title": "Market Update",
            },
        )

        assert response.status_code == 200
        mock_service.create_item.assert_called_once()

        call_args = mock_service.create_item.call_args
        request = call_args[0][1]
        assert request.item_type.value == "url"
        assert request.source_url == "https://example.com/article"


class TestWebhookSecretAuth:
    """Webhook シークレット認証テスト。"""

    def test_webhook_secret_auth_fail(self, mock_service: MagicMock, mock_db: MagicMock) -> None:
        """間違ったシークレットを送ると 401 が返ること。"""
        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("WEBHOOK_SECRET", "mysecret")
            app = create_app()
            app.dependency_overrides[get_db] = lambda: mock_db
            app.dependency_overrides[get_knowledge_service] = lambda: mock_service
            test_client = TestClient(app)

            response = test_client.post(
                "/webhook/tradingview",
                json={"ticker": "BTCUSDT"},
                headers={"X-Webhook-Secret": "wrongsecret"},
            )

        assert response.status_code == 401
        assert "Invalid webhook secret" in response.json()["detail"]

    def test_webhook_secret_auth_pass(self, mock_service: MagicMock, mock_db: MagicMock) -> None:
        """正しいシークレットを送ると 200 が返ること。"""
        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("WEBHOOK_SECRET", "mysecret")
            app = create_app()
            app.dependency_overrides[get_db] = lambda: mock_db
            app.dependency_overrides[get_knowledge_service] = lambda: mock_service
            test_client = TestClient(app)

            response = test_client.post(
                "/webhook/tradingview",
                json={"ticker": "BTCUSDT"},
                headers={"X-Webhook-Secret": "mysecret"},
            )

        assert response.status_code == 200

    def test_webhook_no_secret_configured_passes(
        self, mock_service: MagicMock, mock_db: MagicMock
    ) -> None:
        """WEBHOOK_SECRET が未設定の場合、ヘッダーなしでも 200 が返ること。"""
        with pytest.MonkeyPatch().context() as mp:
            mp.delenv("WEBHOOK_SECRET", raising=False)
            app = create_app()
            app.dependency_overrides[get_db] = lambda: mock_db
            app.dependency_overrides[get_knowledge_service] = lambda: mock_service
            test_client = TestClient(app)

            response = test_client.post(
                "/webhook/generic",
                json={"content": "hello"},
            )

        assert response.status_code == 200


def test_tradingview_webhook_registers_knowledge(
    client: TestClient, mock_service: MagicMock
) -> None:
    """モジュールレベルのテスト: TradingView webhook が正常登録されること。"""
    response = client.post(
        "/webhook/tradingview",
        json={"ticker": "BTCUSDT", "action": "buy", "price": 50000.0},
    )
    assert response.status_code == 200
    assert response.json()["knowledge_item_id"] == 42
    mock_service.create_item.assert_called_once()


def test_generic_webhook_registers_knowledge(client: TestClient, mock_service: MagicMock) -> None:
    """モジュールレベルのテスト: generic webhook が正常登録されること。"""
    response = client.post(
        "/webhook/generic",
        json={"content": "some text"},
    )
    assert response.status_code == 200
    mock_service.create_item.assert_called_once()


def test_webhook_secret_auth_fail() -> None:
    """WEBHOOK_SECRET 設定時に間違ったヘッダーで 401 が返ること。"""
    mock_service = MagicMock()
    mock_db = MagicMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("WEBHOOK_SECRET", "mysecret")
        app = create_app()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_knowledge_service] = lambda: mock_service
        test_client = TestClient(app)

        response = test_client.post(
            "/webhook/tradingview",
            json={"ticker": "BTCUSDT"},
            headers={"X-Webhook-Secret": "wrongsecret"},
        )

    assert response.status_code == 401


def test_webhook_secret_auth_pass() -> None:
    """WEBHOOK_SECRET 設定時に正しいヘッダーで 200 が返ること。"""
    mock_service = MagicMock()
    mock_service.create_item.return_value = _make_mock_item(42)
    mock_db = MagicMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("WEBHOOK_SECRET", "mysecret")
        app = create_app()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_knowledge_service] = lambda: mock_service
        test_client = TestClient(app)

        response = test_client.post(
            "/webhook/tradingview",
            json={"ticker": "BTCUSDT"},
            headers={"X-Webhook-Secret": "mysecret"},
        )

    assert response.status_code == 200


def test_webhook_no_secret_configured_passes() -> None:
    """WEBHOOK_SECRET 未設定時はヘッダーなしでも 200 が返ること。"""
    mock_service = MagicMock()
    mock_service.create_item.return_value = _make_mock_item(42)
    mock_db = MagicMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.delenv("WEBHOOK_SECRET", raising=False)
        app = create_app()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_knowledge_service] = lambda: mock_service
        test_client = TestClient(app)

        response = test_client.post(
            "/webhook/generic",
            json={"content": "hello"},
        )

    assert response.status_code == 200


def test_tradingview_payload_text_format() -> None:
    """ticker / action / price / message が raw_text に含まれること。"""
    mock_service = MagicMock()
    mock_service.create_item.return_value = _make_mock_item(42)
    mock_db = MagicMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.delenv("WEBHOOK_SECRET", raising=False)
        app = create_app()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_knowledge_service] = lambda: mock_service
        test_client = TestClient(app)

        response = test_client.post(
            "/webhook/tradingview",
            json={
                "ticker": "BTCUSDT",
                "action": "buy",
                "price": 100000.5,
                "message": "breakout",
            },
        )

    assert response.status_code == 200
    mock_service.create_item.assert_called_once()

    call_args = mock_service.create_item.call_args
    request = call_args[0][1]
    raw_text = request.raw_text

    assert raw_text is not None
    assert "BTCUSDT" in raw_text
    assert "buy" in raw_text
    assert "100000.5" in raw_text
    assert "breakout" in raw_text
