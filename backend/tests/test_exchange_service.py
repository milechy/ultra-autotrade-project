# backend/tests/test_exchange_service.py
"""Exchange service (rule engine) tests."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.ai.schemas import TradeAction
from app.exchange.client import DummyExchangeClient
from app.exchange.schemas import OrderRequest, OrderStatus
from app.exchange.service import ExchangeService


def _make_settings(**overrides):
    """Create test settings with defaults."""
    settings = MagicMock()
    settings.default_symbol = overrides.get("default_symbol", "BTC/USDT")
    settings.max_order_usd = overrides.get("max_order_usd", Decimal("100"))
    settings.daily_trade_limit = overrides.get("daily_trade_limit", 10)
    settings.cooldown_seconds = overrides.get("cooldown_seconds", 300)
    settings.sandbox = overrides.get("sandbox", True)
    return settings


class TestExchangeService:
    def test_hold_action_skipped(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.HOLD, amount_usd=Decimal("50"))
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SKIPPED
        assert len(client.orders) == 0

    def test_buy_action_executes(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("50"))
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SUCCESS
        assert len(client.orders) == 1

    def test_sell_action_executes(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.SELL, amount_usd=Decimal("50"))
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SUCCESS

    def test_daily_limit_enforced(self):
        client = DummyExchangeClient()
        # Set cooldown_seconds=0 so the cooldown check does not fire before the daily limit check
        service = ExchangeService(
            client=client,
            settings=_make_settings(daily_trade_limit=2, cooldown_seconds=0),
        )
        req = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("10"))
        service.execute_trade(req)
        service.execute_trade(req)
        result = service.execute_trade(req)  # 3rd trade
        assert result.status == OrderStatus.SKIPPED
        assert "limit" in result.message.lower()

    def test_max_order_usd_enforced(self):
        client = DummyExchangeClient()
        service = ExchangeService(
            client=client, settings=_make_settings(max_order_usd=Decimal("50"))
        )
        request = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("100"))
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SKIPPED
        assert "exceed" in result.message.lower() or "max" in result.message.lower()

    def test_dry_run_no_execution(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("50"), dry_run=True)
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SKIPPED
        assert len(client.orders) == 0
        assert "dry" in result.message.lower()

    def test_cooldown_enforced(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings(cooldown_seconds=600))
        req = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("10"))
        service.execute_trade(req)  # First trade
        result = service.execute_trade(req)  # Too soon
        assert result.status == OrderStatus.SKIPPED
        assert "cooldown" in result.message.lower()

    def test_hold_message_describes_reason(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.HOLD, amount_usd=Decimal("50"))
        result = service.execute_trade(request)
        assert result.message is not None
        assert len(result.message) > 0

    def test_successful_buy_has_order_id(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        request = OrderRequest(action=TradeAction.BUY, amount_usd=Decimal("50"))
        result = service.execute_trade(request)
        assert result.status == OrderStatus.SUCCESS
        assert result.order_id is not None
        assert result.price is not None

    def test_get_status_returns_connected(self):
        client = DummyExchangeClient()
        service = ExchangeService(client=client, settings=_make_settings())
        status = service.get_status()
        assert status.connected is True
        assert status.balance_usdt is not None
        assert status.daily_trades_used == 0
