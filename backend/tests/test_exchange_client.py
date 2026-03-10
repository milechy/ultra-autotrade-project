# backend/tests/test_exchange_client.py
"""Exchange client tests."""

import importlib
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.exchange.client import BitFlyerClient, BybitSandboxClient, DummyExchangeClient


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
        settings.hostname = "bybit.com"
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


class TestBybitHostnameSetting:
    """Test BYBIT_HOSTNAME env var in get_exchange_settings()."""

    def test_bybit_eu_hostname_is_set(self):
        """BYBIT_HOSTNAME=bybit.eu results in settings.hostname == 'bybit.eu'."""
        import app.exchange.config as cfg

        env = {
            "BYBIT_HOSTNAME": "bybit.eu",
        }
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.hostname == "bybit.eu"

    def test_bybit_default_hostname(self):
        """When BYBIT_HOSTNAME is not set, hostname defaults to 'bybit.com'."""
        import app.exchange.config as cfg

        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name == "BYBIT_HOSTNAME":
                return None
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_exchange_settings()

        assert settings.hostname == "bybit.com"


class TestBitFlyerClient:
    """Test BitFlyerClient in dry-run mode."""

    def _make_settings(self, api_key: str = "", api_secret: str = "secret") -> MagicMock:
        settings = MagicMock()
        settings.api_key = api_key
        settings.api_secret = api_secret
        settings.sandbox = True
        settings.timeout_seconds = 30
        settings.default_symbol = "BTC/JPY"
        settings.hostname = "bitflyer.com"
        settings.usd_to_jpy_rate = 150.0
        return settings

    def test_bitflyer_dry_run_create_order(self):
        """DRY-RUN で create_market_order が bitflyer-dry-run-XXXX の order_id を返す。"""
        settings = self._make_settings(api_key="")
        client = BitFlyerClient(settings=settings)
        assert client._dry_run is True

        result = client.create_market_order("BTC/JPY", "buy", 0.001)
        assert result["id"].startswith("bitflyer-dry-run-")
        assert result["symbol"] == "BTC/JPY"
        assert result["side"] == "buy"
        assert result["amount"] == 0.001
        assert result["status"] == "closed"
        assert result["filled"] == 0.001
        assert result["type"] == "market"

    def test_bitflyer_dry_run_order_id_increments(self):
        """各注文が連番の ID を持つ。"""
        settings = self._make_settings(api_key="dry-run")
        client = BitFlyerClient(settings=settings)

        r1 = client.create_market_order("BTC/JPY", "buy", 0.001)
        r2 = client.create_market_order("BTC/JPY", "sell", 0.002)

        assert r1["id"] == "bitflyer-dry-run-0001"
        assert r2["id"] == "bitflyer-dry-run-0002"

    def test_bitflyer_dry_run_fetch_balance(self):
        """DRY-RUN で JPY 残高が返る。"""
        settings = self._make_settings(api_key="")
        client = BitFlyerClient(settings=settings)
        balance = client.fetch_balance()

        assert "JPY" in balance
        assert balance["JPY"]["free"] == 1_000_000.0
        assert balance["JPY"]["total"] == 1_000_000.0
        assert "BTC" in balance
        assert balance["BTC"]["free"] == 0.01

    def test_bitflyer_dry_run_fetch_ticker(self):
        """DRY-RUN で BTC/JPY のティッカーが返る。"""
        settings = self._make_settings(api_key="dry-run")
        client = BitFlyerClient(settings=settings)
        ticker = client.fetch_ticker("BTC/JPY")

        assert ticker["symbol"] == "BTC/JPY"
        assert ticker["last"] == BitFlyerClient._DRY_RUN_TICKER_PRICE
        assert ticker["bid"] < ticker["ask"]
        assert ticker["last"] > 0

    def test_bitflyer_api_key_dry_run_string(self):
        """api_key == 'dry-run' でも dry_run モードになる。"""
        settings = self._make_settings(api_key="dry-run")
        client = BitFlyerClient(settings=settings)
        assert client._dry_run is True

    def test_bitflyer_api_key_fallback(self):
        """BITFLYER_API_KEY が EXCHANGE_API_KEY の3番目フォールバックとして機能する。"""
        import app.exchange.config as cfg

        env = {
            "BITFLYER_API_KEY": "bitflyer-key-xyz",
            "BITFLYER_API_SECRET": "bitflyer-secret-xyz",
        }
        with patch.dict("os.environ", env, clear=False):
            # Clear EXCHANGE_API_KEY and BYBIT_API_KEY to test BITFLYER fallback
            original_get_env = cfg.get_env

            def patched_get_env(name: str, required: bool = True) -> str | None:
                if name in ("EXCHANGE_API_KEY", "BYBIT_API_KEY"):
                    return None
                if name in ("EXCHANGE_API_SECRET", "BYBIT_API_SECRET"):
                    return None
                return original_get_env(name, required=required)

            with patch.object(cfg, "get_env", patched_get_env):
                settings = cfg.get_exchange_settings()

        assert settings.api_key == "bitflyer-key-xyz"
        assert settings.api_secret == "bitflyer-secret-xyz"


class TestBtcJpyQuantityCalculation:
    """Test BTC/JPY quantity calculation in ExchangeService."""

    def test_btc_jpy_quantity_calculation(self):
        """amount_usd=100, usd_to_jpy_rate=150, BTC/JPY price=10_000_000 → quantity=0.0015."""
        from app.ai.schemas import TradeAction
        from app.exchange.schemas import OrderRequest
        from app.exchange.service import ExchangeService

        # Mock client that returns a BTC/JPY ticker
        mock_client = MagicMock()
        mock_client.fetch_ticker.return_value = {
            "symbol": "BTC/JPY",
            "last": 10_000_000.0,
            "bid": 9_999_000.0,
            "ask": 10_001_000.0,
            "timestamp": None,
        }
        mock_client.create_market_order.return_value = {
            "id": "test-order-0001",
            "symbol": "BTC/JPY",
            "type": "market",
            "side": "buy",
            "amount": 0.0015,
            "price": 10_000_000.0,
            "status": "closed",
            "filled": 0.0015,
            "cost": 15000.0,
        }

        settings = MagicMock()
        settings.default_symbol = "BTC/JPY"
        settings.max_order_usd = Decimal("1000")
        settings.daily_trade_limit = 10
        settings.cooldown_seconds = 0
        settings.sandbox = True
        settings.usd_to_jpy_rate = 150.0

        service = ExchangeService(client=mock_client, settings=settings)

        request = OrderRequest(
            action=TradeAction.BUY,
            symbol="BTC/JPY",
            amount_usd=Decimal("100"),
            dry_run=False,
        )

        service.execute_trade(request)

        # Verify create_market_order was called with the correct quantity
        # 100 USD * 150 JPY/USD = 15,000 JPY / 10,000,000 JPY/BTC = 0.0015 BTC
        call_args = mock_client.create_market_order.call_args
        assert call_args is not None
        _, _, quantity = call_args[0]
        assert abs(quantity - 0.0015) < 1e-10


class TestAppEnvProdMode:
    """Test APP_ENV=prod forces sandbox=False in get_exchange_settings()."""

    def test_app_env_prod_forces_sandbox_false(self):
        """APP_ENV=prod → settings.sandbox is False."""
        import importlib

        import app.exchange.config as cfg

        env = {"APP_ENV": "prod"}
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.sandbox is False
        assert settings.app_env == "prod"

    def test_app_env_prod_overrides_exchange_sandbox_true(self):
        """APP_ENV=prod overrides EXCHANGE_SANDBOX=true."""
        import importlib

        import app.exchange.config as cfg

        env = {"APP_ENV": "prod", "EXCHANGE_SANDBOX": "true"}
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.sandbox is False

    def test_app_env_non_prod_keeps_sandbox_true(self):
        """APP_ENV=staging (non-prod) → sandbox defaults to True."""
        import app.exchange.config as cfg

        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name == "APP_ENV":
                return "staging"
            if name in ("EXCHANGE_SANDBOX", "BYBIT_SANDBOX"):
                return None
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_exchange_settings()

        assert settings.sandbox is True

    def test_app_env_field_set_correctly(self):
        """settings.app_env matches APP_ENV env var."""
        import importlib

        import app.exchange.config as cfg

        env = {"APP_ENV": "prod"}
        with patch.dict("os.environ", env, clear=False):
            importlib.reload(cfg)
            settings = cfg.get_exchange_settings()

        assert settings.app_env == "prod"


class TestGetBitflyerSettings:
    """Test get_bitflyer_settings() uses BITFLYER_* keys directly."""

    def test_bitflyer_settings_uses_bitflyer_api_key(self):
        """BITFLYER_API_KEY → settings.api_key (not BYBIT_API_KEY)."""
        import app.exchange.config as cfg

        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name == "BITFLYER_API_KEY":
                return "bitflyer-real-key"
            if name == "BITFLYER_API_SECRET":
                return "bitflyer-real-secret"
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_bitflyer_settings()

        assert settings.api_key == "bitflyer-real-key"
        assert settings.api_secret == "bitflyer-real-secret"

    def test_bitflyer_settings_default_symbol_is_btc_jpy(self):
        """get_bitflyer_settings() defaults default_symbol to 'BTC/JPY'."""
        import app.exchange.config as cfg

        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name == "EXCHANGE_DEFAULT_SYMBOL":
                return None
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_bitflyer_settings()

        assert settings.default_symbol == "BTC/JPY"

    def test_bitflyer_settings_sandbox_always_true(self):
        """bitFlyer settings sandbox is always True (no sandbox available)."""
        import app.exchange.config as cfg

        settings = cfg.get_bitflyer_settings()
        assert settings.sandbox is True

    def test_bitflyer_settings_ignores_bybit_key(self):
        """When BYBIT_API_KEY is set, bitFlyer settings uses BITFLYER_API_KEY instead."""
        import app.exchange.config as cfg

        original_get_env = cfg.get_env

        def patched_get_env(name: str, required: bool = True) -> str | None:
            if name == "BYBIT_API_KEY":
                return "bybit-key-should-be-ignored"
            if name == "BITFLYER_API_KEY":
                return "bitflyer-correct-key"
            if name == "BYBIT_API_SECRET":
                return "bybit-secret-should-be-ignored"
            if name == "BITFLYER_API_SECRET":
                return "bitflyer-correct-secret"
            return original_get_env(name, required=required)

        with patch.object(cfg, "get_env", patched_get_env):
            settings = cfg.get_bitflyer_settings()

        assert settings.api_key == "bitflyer-correct-key"
        assert settings.api_secret == "bitflyer-correct-secret"
