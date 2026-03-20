# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_exchange_okx_client.py
"""OKXClient dry-run mode tests."""

from unittest.mock import MagicMock

from app.exchange.okx_client import OKXClient


def _make_settings(api_key: str, api_secret: str = "secret") -> MagicMock:
    settings = MagicMock()
    settings.api_key = api_key
    settings.api_secret = api_secret
    settings.passphrase = ""
    settings.sandbox = True
    settings.timeout_seconds = 30
    settings.default_symbol = "BTC/USDT"
    settings.hostname = "okx.com"
    return settings


class TestOKXClientDryRun:
    """Test OKXClient in dry-run mode (no real API calls)."""

    def test_dry_run_when_api_key_empty(self):
        """Empty api_key triggers dry-run mode."""
        settings = _make_settings(api_key="")
        client = OKXClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_when_api_key_is_dry_run_string(self):
        """api_key == 'dry-run' triggers dry-run mode."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_create_order_returns_correct_structure(self):
        """create_market_order in dry-run returns expected dict keys."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        result = client.create_market_order("BTC/USDT", "buy", 0.001)

        assert result["symbol"] == "BTC/USDT"
        assert result["side"] == "buy"
        assert result["amount"] == 0.001
        assert result["status"] == "closed"
        assert result["filled"] == 0.001
        assert result["type"] == "market"

    def test_dry_run_fetch_balance_contains_usdt(self):
        """fetch_balance in dry-run returns a USDT balance entry."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        balance = client.fetch_balance()

        assert "USDT" in balance
        assert balance["USDT"]["free"] > 0
        assert balance["USDT"]["total"] > 0

    def test_dry_run_fetch_balance_contains_btc(self):
        """fetch_balance in dry-run returns a BTC balance entry."""
        settings = _make_settings(api_key="")
        client = OKXClient(settings=settings)
        balance = client.fetch_balance()

        assert "BTC" in balance
        assert balance["BTC"]["total"] > 0

    def test_dry_run_fetch_ticker_returns_symbol(self):
        """fetch_ticker in dry-run returns correct symbol."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        ticker = client.fetch_ticker("ETH/USDT")

        assert ticker["symbol"] == "ETH/USDT"

    def test_dry_run_fetch_ticker_has_positive_last_price(self):
        """fetch_ticker in dry-run returns a positive last price."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USDT")

        assert ticker["last"] > 0

    def test_dry_run_order_id_prefix(self):
        """Order ID should start with 'okx-dry-run-'."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        result = client.create_market_order("BTC/USDT", "buy", 0.001)

        assert result["id"].startswith("okx-dry-run-")

    def test_dry_run_order_id_increments(self):
        """Each order gets a unique, incrementing ID."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)

        r1 = client.create_market_order("BTC/USDT", "buy", 0.001)
        r2 = client.create_market_order("BTC/USDT", "sell", 0.002)

        assert r1["id"] == "okx-dry-run-0001"
        assert r2["id"] == "okx-dry-run-0002"

    def test_dry_run_ticker_bid_lower_than_ask(self):
        """fetch_ticker bid is lower than ask in dry-run mode."""
        settings = _make_settings(api_key="dry-run")
        client = OKXClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USDT")

        assert ticker["bid"] < ticker["ask"]

    def test_dry_run_uses_fixed_ticker_price(self):
        """Dry-run orders use the fixed ticker price constant."""
        settings = _make_settings(api_key="")
        client = OKXClient(settings=settings)
        result = client.create_market_order("BTC/USDT", "buy", 0.001)

        assert result["price"] == OKXClient._DRY_RUN_TICKER_PRICE
        assert result["cost"] == 0.001 * OKXClient._DRY_RUN_TICKER_PRICE