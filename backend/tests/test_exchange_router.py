# backend/tests/test_exchange_router.py
"""Exchange router tests using FastAPI TestClient with dependency overrides."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exchange.router import get_exchange_service
from app.exchange.schemas import (
    ExchangeStatusResponse,
    OrderResult,
    OrderSide,
    OrderStatus,
)
from app.main import create_app


def _make_order_result(
    status: OrderStatus = OrderStatus.SUCCESS,
    order_id: str = "order-123",
    side: OrderSide = OrderSide.BUY,
    symbol: str = "BTC/USDT",
    amount_usd: Decimal = Decimal("50"),
    price: Decimal = Decimal("45000"),
    message: str = "Order executed successfully",
) -> OrderResult:
    return OrderResult(
        order_id=order_id,
        status=status,
        side=side,
        symbol=symbol,
        amount_usd=amount_usd,
        price=price,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )


def _make_status_response(
    connected: bool = True,
    balance_usdt: Decimal = Decimal("1000"),
    daily_trades_used: int = 0,
    daily_trade_limit: int = 10,
) -> ExchangeStatusResponse:
    return ExchangeStatusResponse(
        sandbox_mode=True,
        connected=connected,
        balance_usdt=balance_usdt,
        daily_trades_used=daily_trades_used,
        daily_trade_limit=daily_trade_limit,
        last_trade_at=None,
    )


@pytest.fixture()
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def client(mock_service: MagicMock) -> TestClient:
    app = create_app()
    # Override the lru_cache'd dependency with our mock
    app.dependency_overrides[get_exchange_service] = lambda: mock_service
    return TestClient(app)


class TestGetExchangeServiceFactory:
    """Test the get_exchange_service factory function directly."""

    def test_factory_returns_dummy_client_when_env_is_dummy(self) -> None:
        """get_exchange_service returns ExchangeService with DummyExchangeClient."""
        import os

        # Clear lru_cache so the factory re-runs with our env var
        from app.exchange import router as exchange_router_mod
        exchange_router_mod.get_exchange_service.cache_clear()

        with patch.dict(os.environ, {"EXCHANGE_CLIENT_TYPE": "dummy"}):
            service = exchange_router_mod.get_exchange_service()

        from app.exchange.client import DummyExchangeClient
        from app.exchange.service import ExchangeService
        assert isinstance(service, ExchangeService)
        assert isinstance(service._client, DummyExchangeClient)

        # Clean up cache after test
        exchange_router_mod.get_exchange_service.cache_clear()

    def test_factory_returns_sandbox_client_when_env_is_sandbox(self) -> None:
        """get_exchange_service returns ExchangeService with BybitSandboxClient for non-dummy."""
        import os

        from app.exchange import router as exchange_router_mod
        exchange_router_mod.get_exchange_service.cache_clear()

        with patch.dict(os.environ, {"EXCHANGE_CLIENT_TYPE": "sandbox"}):
            service = exchange_router_mod.get_exchange_service()

        from app.exchange.client import BybitSandboxClient
        from app.exchange.service import ExchangeService
        assert isinstance(service, ExchangeService)
        assert isinstance(service._client, BybitSandboxClient)

        exchange_router_mod.get_exchange_service.cache_clear()


class TestPostExchangeOrder:
    """POST /exchange/order"""

    def test_post_order_buy_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /exchange/order with BUY action returns OrderResult with status SUCCESS."""
        mock_service.execute_trade.return_value = _make_order_result(
            status=OrderStatus.SUCCESS, order_id="order-abc", side=OrderSide.BUY
        )

        response = client.post(
            "/exchange/order",
            json={"action": "BUY", "amount_usd": "50", "symbol": "BTC/USDT"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["order_id"] == "order-abc"
        assert data["side"] == "buy"
        mock_service.execute_trade.assert_called_once()

    def test_post_order_sell_success(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /exchange/order with SELL action returns OrderResult."""
        mock_service.execute_trade.return_value = _make_order_result(
            status=OrderStatus.SUCCESS, side=OrderSide.SELL
        )

        response = client.post(
            "/exchange/order",
            json={"action": "SELL", "amount_usd": "30"},
        )

        assert response.status_code == 200
        assert response.json()["side"] == "sell"

    def test_post_order_hold_skipped(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /exchange/order with HOLD returns SKIPPED result."""
        mock_service.execute_trade.return_value = OrderResult(
            order_id=None,
            status=OrderStatus.SKIPPED,
            side=None,
            symbol="BTC/USDT",
            amount_usd=Decimal("50"),
            price=None,
            message="Action is HOLD - no trade executed",
            timestamp=datetime.now(timezone.utc),
        )

        response = client.post(
            "/exchange/order",
            json={"action": "HOLD", "amount_usd": "50"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert data["order_id"] is None

    def test_post_order_internal_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /exchange/order returns 500 when service raises unexpected exception."""
        mock_service.execute_trade.side_effect = RuntimeError("Unexpected crash")

        response = client.post(
            "/exchange/order",
            json={"action": "BUY", "amount_usd": "50"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    def test_post_order_dry_run(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /exchange/order with dry_run=true returns SKIPPED."""
        mock_service.execute_trade.return_value = OrderResult(
            order_id=None,
            status=OrderStatus.SKIPPED,
            side=None,
            symbol="BTC/USDT",
            amount_usd=Decimal("50"),
            price=None,
            message="Dry run - order not executed",
            timestamp=datetime.now(timezone.utc),
        )

        response = client.post(
            "/exchange/order",
            json={"action": "BUY", "amount_usd": "50", "dry_run": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert "Dry run" in data["message"]

    def test_post_order_invalid_action_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /exchange/order with invalid action returns 422 from Pydantic validation."""
        response = client.post(
            "/exchange/order",
            json={"action": "INVALID_ACTION", "amount_usd": "50"},
        )

        assert response.status_code == 422

    def test_post_order_missing_amount_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """POST /exchange/order without amount_usd returns 422."""
        response = client.post(
            "/exchange/order",
            json={"action": "BUY"},
        )

        assert response.status_code == 422

    def test_post_order_failed_result(self, client: TestClient, mock_service: MagicMock) -> None:
        """POST /exchange/order returns FAILED result when ticker fetch fails."""
        mock_service.execute_trade.return_value = OrderResult(
            order_id=None,
            status=OrderStatus.FAILED,
            side=None,
            symbol="BTC/USDT",
            amount_usd=Decimal("50"),
            price=None,
            message="Failed to fetch ticker: connection error",
            timestamp=datetime.now(timezone.utc),
        )

        response = client.post(
            "/exchange/order",
            json={"action": "BUY", "amount_usd": "50"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "Failed to fetch ticker" in data["message"]


class TestGetExchangeStatus:
    """GET /exchange/status"""

    def test_get_status_connected(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /exchange/status returns status with connected=True."""
        mock_service.get_status.return_value = _make_status_response(
            connected=True, balance_usdt=Decimal("2500"), daily_trades_used=3
        )

        response = client.get("/exchange/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["sandbox_mode"] is True
        assert data["daily_trades_used"] == 3
        assert data["daily_trade_limit"] == 10

    def test_get_status_disconnected(self, client: TestClient, mock_service: MagicMock) -> None:
        """GET /exchange/status returns connected=False when exchange is down."""
        mock_service.get_status.return_value = _make_status_response(
            connected=False, balance_usdt=None
        )

        response = client.get("/exchange/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["balance_usdt"] is None

    def test_get_status_internal_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /exchange/status returns 500 on unexpected exception."""
        mock_service.get_status.side_effect = RuntimeError("Status check exploded")

        response = client.get("/exchange/status")

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    def test_get_status_daily_limit_reached(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /exchange/status shows when daily limit is reached."""
        mock_service.get_status.return_value = _make_status_response(
            connected=True, daily_trades_used=10, daily_trade_limit=10
        )

        response = client.get("/exchange/status")

        assert response.status_code == 200
        data = response.json()
        assert data["daily_trades_used"] == data["daily_trade_limit"]

    def test_get_status_with_last_trade_at(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """GET /exchange/status includes last_trade_at when trades have occurred."""
        last_trade = datetime.now(timezone.utc)
        status_response = ExchangeStatusResponse(
            sandbox_mode=True,
            connected=True,
            balance_usdt=Decimal("500"),
            daily_trades_used=1,
            daily_trade_limit=10,
            last_trade_at=last_trade,
        )
        mock_service.get_status.return_value = status_response

        response = client.get("/exchange/status")

        assert response.status_code == 200
        data = response.json()
        assert data["last_trade_at"] is not None
        assert data["daily_trades_used"] == 1
