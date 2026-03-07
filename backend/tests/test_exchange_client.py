# backend/tests/test_exchange_client.py
"""Exchange client tests."""

import importlib
from unittest.mock import MagicMock, patch

from app.exchange.client import BybitSandboxClient, DummyExchangeClient


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


class TestBybitSandboxClientDryRun:
    """Test BybitSandboxClient dry-run mode (no real API calls)."""

    def _make_settings(self, api_key: str, api_secret: str = "secret") -> MagicMock:
        settings = MagicMock()
        settings.api_key = api_key
        settings.api_secret = api_secret
        settings.sandbox = True
        settings.timeout_seconds = 30
        settings.default_symbol = "BTC/USDT"
        return settings

    def test_dry_run_when_api_key_empty(self):
        """Empty api_key triggers dry-run mode."""
        settings = self._make_settings(api_key="")
        client = BybitSandboxClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_when_api_key_is_dry_run_string(self):
        """api_key == 'dry-run' triggers dry-run mode."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        assert client._dry_run is True

    def test_dry_run_counter_starts_at_zero(self):
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        assert client._dry_run_counter == 0

    def test_dry_run_create_order_returns_correct_structure(self):
        """create_market_order in dry-run returns expected dict keys."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        result = client.create_market_order("BTC/USDT", "buy", 0.001)

        assert result["id"].startswith("dry-run-")
        assert result["symbol"] == "BTC/USDT"
        assert result["side"] == "buy"
        assert result["amount"] == 0.001
        assert result["status"] == "closed"
        assert result["filled"] == 0.001
        assert result["type"] == "market"

    def test_dry_run_create_order_id_increments(self):
        """Each order gets a unique, incrementing ID."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)

        r1 = client.create_market_order("BTC/USDT", "buy", 0.001)
        r2 = client.create_market_order("BTC/USDT", "sell", 0.002)

        assert r1["id"] == "dry-run-0001"
        assert r2["id"] == "dry-run-0002"

    def test_dry_run_create_order_uses_fixed_price(self):
        """Dry-run orders use the fixed ticker price constant."""
        settings = self._make_settings(api_key="")
        client = BybitSandboxClient(settings=settings)
        result = client.create_market_order("BTC/USDT", "buy", 0.001)

        assert result["price"] == BybitSandboxClient._DRY_RUN_TICKER_PRICE
        assert result["cost"] == 0.001 * BybitSandboxClient._DRY_RUN_TICKER_PRICE

    def test_dry_run_fetch_balance_contains_usdt(self):
        """fetch_balance in dry-run returns a USDT balance entry."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        balance = client.fetch_balance()

        assert "USDT" in balance
        assert balance["USDT"]["free"] > 0
        assert balance["USDT"]["total"] > 0

    def test_dry_run_fetch_balance_contains_btc(self):
        """fetch_balance in dry-run returns a BTC balance entry."""
        settings = self._make_settings(api_key="")
        client = BybitSandboxClient(settings=settings)
        balance = client.fetch_balance()

        assert "BTC" in balance
        assert balance["BTC"]["total"] > 0

    def test_dry_run_fetch_ticker_returns_symbol(self):
        """fetch_ticker in dry-run returns correct symbol."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        ticker = client.fetch_ticker("ETH/USDT")

        assert ticker["symbol"] == "ETH/USDT"

    def test_dry_run_fetch_ticker_has_positive_last_price(self):
        """fetch_ticker in dry-run returns a positive last price."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USDT")

        assert ticker["last"] > 0

    def test_dry_run_fetch_ticker_bid_lower_than_ask(self):
        """fetch_ticker bid is lower than ask in dry-run mode."""
        settings = self._make_settings(api_key="")
        client = BybitSandboxClient(settings=settings)
        ticker = client.fetch_ticker("BTC/USDT")

        assert ticker["bid"] < ticker["ask"]

    def test_dry_run_sell_order(self):
        """Sell orders are handled correctly in dry-run mode."""
        settings = self._make_settings(api_key="dry-run")
        client = BybitSandboxClient(settings=settings)
        result = client.create_market_order("ETH/USDT", "sell", 1.5)

        assert result["side"] == "sell"
        assert result["symbol"] == "ETH/USDT"
        assert result["amount"] == 1.5
        assert result["status"] == "closed"


class TestGetExchangeSettingsFallback:
    """Test BYBIT_* env var fallback in get_exchange_settings()."""

    def test_bybit_api_key_used_when_exchange_api_key_missing(self):
        """BYBIT_API_KEY is used when EXCHANGE_API_KEY is not set."""
        import app.exchange.config as cfg

        env = {
            "BYBIT_API_KEY": "bybit-key-123",
            "BYBIT_API_SECRET": "bybit-secret-456",
        }
        with patch.dict("os.environ", env, clear=False):
            # Reload to clear any cached state (get_env reads os.environ directly)
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.api_key == "bybit-key-123"
        assert settings.api_secret == "bybit-secret-456"

    def test_exchange_api_key_takes_priority_over_bybit(self):
        """EXCHANGE_API_KEY takes priority over BYBIT_API_KEY when both are set."""
        import app.exchange.config as cfg

        env = {
            "EXCHANGE_API_KEY": "exchange-key",
            "EXCHANGE_API_SECRET": "exchange-secret",
            "BYBIT_API_KEY": "bybit-key",
            "BYBIT_API_SECRET": "bybit-secret",
        }
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.api_key == "exchange-key"
        assert settings.api_secret == "exchange-secret"

    def test_bybit_sandbox_fallback(self):
        """BYBIT_SANDBOX is used when EXCHANGE_SANDBOX is not set."""
        import app.exchange.config as cfg

        env = {
            "BYBIT_API_KEY": "key",
            "BYBIT_API_SECRET": "secret",
            "BYBIT_SANDBOX": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.sandbox is True

    def test_empty_keys_trigger_dry_run(self):
        """When no API key env vars are set, api_key is empty (dry-run mode)."""
        import app.exchange.config as cfg

        # Patch get_env to return None for all key-related vars
        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name in (
                "EXCHANGE_API_KEY",
                "EXCHANGE_API_SECRET",
                "BYBIT_API_KEY",
                "BYBIT_API_SECRET",
            ):
                return None
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_exchange_settings()

        assert settings.api_key == ""
        assert settings.api_secret == ""
