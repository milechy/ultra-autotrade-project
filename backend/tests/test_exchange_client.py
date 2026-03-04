# backend/tests/test_exchange_client.py
"""Exchange client tests."""

from app.exchange.client import DummyExchangeClient


class TestDummyExchangeClient:
    def test_create_order_records(self):
        client = DummyExchangeClient()
        result = client.create_market_order("BTC/USDT", "buy", 0.001)
        assert result["status"] == "closed"
        assert result["side"] == "buy"
        assert len(client.orders) == 1

    def test_fetch_balance(self):
        client = DummyExchangeClient()
        balance = client.fetch_balance()
        assert "USDT" in balance
        assert balance["USDT"]["total"] > 0

    def test_fetch_ticker(self):
        client = DummyExchangeClient()
        ticker = client.fetch_ticker("BTC/USDT")
        assert ticker["symbol"] == "BTC/USDT"
        assert ticker["last"] > 0

    def test_multiple_orders_tracked(self):
        client = DummyExchangeClient()
        client.create_market_order("BTC/USDT", "buy", 0.001)
        client.create_market_order("ETH/USDT", "sell", 0.1)
        assert len(client.orders) == 2

    def test_create_order_returns_order_id(self):
        client = DummyExchangeClient()
        result = client.create_market_order("BTC/USDT", "buy", 0.001)
        assert "id" in result
        assert result["id"].startswith("dummy-order-")

    def test_create_order_increments_counter(self):
        client = DummyExchangeClient()
        order1 = client.create_market_order("BTC/USDT", "buy", 0.001)
        order2 = client.create_market_order("BTC/USDT", "sell", 0.002)
        assert order1["id"] != order2["id"]

    def test_fetch_balance_has_btc(self):
        client = DummyExchangeClient()
        balance = client.fetch_balance()
        assert "BTC" in balance
        assert balance["BTC"]["total"] > 0

    def test_fetch_ticker_has_bid_ask(self):
        client = DummyExchangeClient()
        ticker = client.fetch_ticker("ETH/USDT")
        assert "bid" in ticker
        assert "ask" in ticker
        assert ticker["ask"] > ticker["bid"]
