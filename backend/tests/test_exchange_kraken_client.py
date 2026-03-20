# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_exchange_kraken_client.py
"""KrakenClient dry-run mode tests."""

from unittest.mock import MagicMock

from app.exchange.kraken_client import KrakenClient


def _make_settings(api_key: str, api_secret: str = "secret") -> MagicMock:
    settings = MagicMock()
    settings.api_key = api_key
    settings.api_secret = api_secret
    settings.sandbox = True
    settings.timeout_seconds = 30
    settings.default_symbol = "BTC/USD"
    settings.hostname = "kraken.com"
    return settings


class TestKrakenClientDryRun:
    """Test KrakenClient in dry-run mode (no real API calls)."""

    def test_dry_run_when_api_key_empty(self):
        """Empty api_key triggers dry-run mode."""
        settings = _make_settings(api_key="")
        client = KrakenClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_when_api_key_is_dry_run_string(self):
        """api_key == 'dry-run' triggers dry-run mode."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_create_order_returns_correct_structure(self):
        """create_market_order in dry-run returns expected dict keys."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        result = client.create_market_order("BTC/USD", "buy", 0.001)

        assert result["symbol"] == "BTC/USD"
        assert result["side"] == "buy"
        assert result["amount"] == 0.001
        assert result["status"] == "closed"
        assert result["filled"] == 0.001
        assert result["type"] == "market"

    def test_dry_run_fetch_balance_contains_usd(self):
        """fetch_balance in dry-run returns a USD balance entry (Kraken uses USD not USDT)."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        balance = client.fetch_balance()

        assert "USD" in balance
        assert balance["USD"]["free"] > 0
        assert balance["USD"]["total"] > 0

    def test_dry_run_fetch_balance_contains_btc(self):
        """fetch_balance in dry-run returns a BTC balance entry."""
        settings = _make_settings(api_key="")
        client = KrakenClient(settings=settings)
        balance = client.fetch_balance()

        assert "BTC" in balance
        assert balance["BTC"]["total"] > 0

    def test_dry_run_fetch_ticker_returns_symbol(self):
        """fetch_ticker in dry-run returns correct symbol."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USD")

        assert ticker["symbol"] == "BTC/USD"

    def test_dry_run_fetch_ticker_has_positive_last_price(self):
        """fetch_ticker in dry-run returns a positive last price."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USD")

        assert ticker["last"] > 0

    def test_dry_run_order_id_prefix(self):
        """Order ID should start with 'kraken-dry-run-'."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        result = client.create_market_order("BTC/USD", "buy", 0.001)

        assert result["id"].startswith("kraken-dry-run-")

    def test_dry_run_order_id_increments(self):
        """Each order gets a unique, incrementing ID."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)

        r1 = client.create_market_order("BTC/USD", "buy", 0.001)
        r2 = client.create_market_order("ETH/USD", "sell", 0.5)

        assert r1["id"] == "kraken-dry-run-0001"
        assert r2["id"] == "kraken-dry-run-0002"

    def test_dry_run_ticker_bid_lower_than_ask(self):
        """fetch_ticker bid is lower than ask in dry-run mode."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USD")

        assert ticker["bid"] < ticker["ask"]

    def test_dry_run_uses_fixed_ticker_price(self):
        """Dry-run orders use the fixed ticker price constant."""
        settings = _make_settings(api_key="")
        client = KrakenClient(settings=settings)
        result = client.create_market_order("BTC/USD", "buy", 0.001)

        assert result["price"] == KrakenClient._DRY_RUN_TICKER_PRICE
        assert result["cost"] == 0.001 * KrakenClient._DRY_RUN_TICKER_PRICE

    def test_dry_run_no_usdt_in_balance(self):
        """Kraken uses USD (not USDT), so USDT should not be in balance."""
        settings = _make_settings(api_key="dry-run")
        client = KrakenClient(settings=settings)
        balance = client.fetch_balance()

        assert "USDT" not in balance