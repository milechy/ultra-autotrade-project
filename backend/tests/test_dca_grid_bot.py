# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_dca_grid_bot.py
"""GridBotService のユニットテスト。"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.dca.grid_bot import GridBotService, GridConfig, GridStatus, get_grid_config_from_env
from app.exchange.client import DummyExchangeClient
from app.exchange.service import ExchangeService


def _make_exchange_service() -> ExchangeService:
    """DummyExchangeClient を使った ExchangeService を生成する。"""
    client = DummyExchangeClient()
    return ExchangeService(client=client)


def _make_grid_config(**kwargs: object) -> GridConfig:
    """テスト用 GridConfig を生成するヘルパー。"""
    defaults: dict[str, object] = {
        "upper_price": Decimal("60000"),
        "lower_price": Decimal("40000"),
        "grid_count": 10,
        "symbol": "BTC/USDT",
        "amount_per_grid_usd": Decimal("10"),
        "enabled": True,
        "dry_run": True,
    }
    defaults.update(kwargs)
    return GridConfig(**defaults)  # type: ignore[arg-type]


class TestCalculateLevels:
    """GridBotService.calculate_levels のテスト。"""

    def test_calculate_levels_count(self):
        """grid_count + 1 個のレベルが生成される。"""
        service = GridBotService(_make_exchange_service())
        levels = service.calculate_levels(
            upper=Decimal("60000"),
            lower=Decimal("40000"),
            count=10,
            current_price=Decimal("50000"),
        )
        assert len(levels) == 11  # count + 1

    def test_calculate_levels_prices_in_range(self):
        """全てのグリッド価格が lower〜upper の範囲内にある。"""
        service = GridBotService(_make_exchange_service())
        upper = Decimal("60000")
        lower = Decimal("40000")
        levels = service.calculate_levels(
            upper=upper, lower=lower, count=10, current_price=Decimal("50000")
        )
        for level in levels:
            assert lower <= level.price <= upper

    def test_calculate_levels_buy_below_current(self):
        """current_price 以下のレベルは 'buy' になる。"""
        service = GridBotService(_make_exchange_service())
        current = Decimal("50000")
        levels = service.calculate_levels(
            upper=Decimal("60000"),
            lower=Decimal("40000"),
            count=10,
            current_price=current,
        )
        for level in levels:
            if level.price <= current:
                assert level.side == "buy", f"Price {level.price} should be buy"

    def test_calculate_levels_sell_above_current(self):
        """current_price より上のレベルは 'sell' になる。"""
        service = GridBotService(_make_exchange_service())
        current = Decimal("50000")
        levels = service.calculate_levels(
            upper=Decimal("60000"),
            lower=Decimal("40000"),
            count=10,
            current_price=current,
        )
        for level in levels:
            if level.price > current:
                assert level.side == "sell", f"Price {level.price} should be sell"

    def test_calculate_levels_uses_decimal_only(self):
        """全てのグリッド価格が Decimal 型である。"""
        service = GridBotService(_make_exchange_service())
        levels = service.calculate_levels(
            upper=Decimal("60000"),
            lower=Decimal("40000"),
            count=5,
            current_price=Decimal("50000"),
        )
        for level in levels:
            assert isinstance(level.price, Decimal), f"Price {level.price!r} should be Decimal"

    def test_calculate_levels_invalid_count(self):
        """grid_count < 2 の場合は ValueError を発生させる。"""
        service = GridBotService(_make_exchange_service())
        with pytest.raises(ValueError, match="grid_count must be >= 2"):
            service.calculate_levels(
                upper=Decimal("60000"),
                lower=Decimal("40000"),
                count=1,
                current_price=Decimal("50000"),
            )

    def test_calculate_levels_invalid_range(self):
        """upper <= lower の場合は ValueError を発生させる。"""
        service = GridBotService(_make_exchange_service())
        with pytest.raises(ValueError, match="upper_price must be > lower_price"):
            service.calculate_levels(
                upper=Decimal("40000"),
                lower=Decimal("60000"),
                count=10,
                current_price=Decimal("50000"),
            )

    def test_calculate_levels_equal_upper_lower_raises(self):
        """upper == lower の場合も ValueError を発生させる。"""
        service = GridBotService(_make_exchange_service())
        with pytest.raises(ValueError, match="upper_price must be > lower_price"):
            service.calculate_levels(
                upper=Decimal("50000"),
                lower=Decimal("50000"),
                count=10,
                current_price=Decimal("50000"),
            )


class TestExecuteDisabled:
    """execute() で enabled=False のテスト。"""

    def test_execute_disabled(self):
        """enabled=False の場合は注文をスキップして disabled ステータスを返す。"""
        service = GridBotService(_make_exchange_service())
        config = _make_grid_config(enabled=False)
        status = service.execute(config)

        assert status.enabled is False
        assert len(status.levels) == 0
        assert status.total_orders == 0
        assert status.filled_orders == 0


class TestExecuteDryRun:
    """execute() の DRY-RUN テスト。"""

    def test_execute_dry_run(self):
        """DummyExchangeClient を使って execute() が valid GridStatus を返す。"""
        service = GridBotService(_make_exchange_service())
        config = _make_grid_config(dry_run=True)
        status = service.execute(config)

        assert isinstance(status, GridStatus)
        assert status.enabled is True
        assert status.symbol == "BTC/USDT"
        assert status.upper_price == Decimal("60000")
        assert status.lower_price == Decimal("40000")
        assert status.grid_count == 10
        assert len(status.levels) == 11  # grid_count + 1
        assert status.total_orders == 11
        assert status.current_price is not None
        assert isinstance(status.pnl_usd, Decimal)

    def test_execute_returns_correct_symbol(self):
        """execute() が config.symbol を正しく返す。"""
        service = GridBotService(_make_exchange_service())
        config = _make_grid_config(symbol="ETH/USDT")
        status = service.execute(config)
        assert status.symbol == "ETH/USDT"

    def test_execute_pnl_is_zero(self):
        """現段階では pnl_usd は常にゼロを返す。"""
        service = GridBotService(_make_exchange_service())
        config = _make_grid_config()
        status = service.execute(config)
        assert status.pnl_usd == Decimal("0")


class TestGetGridConfigFromEnv:
    """get_grid_config_from_env() のテスト。"""

    def test_get_grid_config_from_env_defaults(self):
        """デフォルト値が正しく設定される。"""
        with patch.dict("os.environ", {}, clear=False):
            # 環境変数をクリアせずにデフォルト値をテスト
            config = get_grid_config_from_env()

        assert isinstance(config.upper_price, Decimal)
        assert isinstance(config.lower_price, Decimal)
        assert isinstance(config.amount_per_grid_usd, Decimal)
        assert config.symbol == "BTC/USDT"
        assert config.grid_count == 10

    def test_get_grid_config_from_env_custom_values(self):
        """カスタム環境変数が正しく読み取られる。"""
        env = {
            "GRID_ENABLED": "true",
            "GRID_UPPER": "70000",
            "GRID_LOWER": "50000",
            "GRID_COUNT": "20",
            "GRID_SYMBOL": "ETH/USDT",
            "GRID_AMOUNT_USD": "25",
            "GRID_DRY_RUN": "false",
        }
        with patch.dict("os.environ", env, clear=False):
            config = get_grid_config_from_env()

        assert config.enabled is True
        assert config.upper_price == Decimal("70000")
        assert config.lower_price == Decimal("50000")
        assert config.grid_count == 20
        assert config.symbol == "ETH/USDT"
        assert config.amount_per_grid_usd == Decimal("25")
        assert config.dry_run is False

    def test_get_grid_config_from_env_enabled_false_by_default(self):
        """GRID_ENABLED が未設定の場合は False（安全側）。"""
        with patch.dict("os.environ", {"GRID_ENABLED": ""}, clear=False):
            config = get_grid_config_from_env()
        assert config.enabled is False

    def test_get_grid_config_from_env_dry_run_true_by_default(self):
        """GRID_DRY_RUN が未設定の場合は True（安全側）。"""
        import os

        env = {k: v for k, v in os.environ.items() if k != "GRID_DRY_RUN"}
        with patch.dict("os.environ", env, clear=True):
            config = get_grid_config_from_env()
        assert config.dry_run is True
