# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_dca_service.py

"""
DCAService のユニットテスト。

ExchangeService はモックを使用し、実際の取引所には接続しない。
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.dca.schemas import DCAConfig, DCAExecutionResult, DCAFrequency
from app.dca.service import DCAService
from app.exchange.schemas import OrderResult, OrderStatus
from app.exchange.service import ExchangeService


def _make_config(**kwargs: object) -> DCAConfig:
    """テスト用 DCAConfig を生成するヘルパー。"""
    defaults: dict[str, object] = {
        "enabled": True,
        "symbol": "BTC/USDT",
        "amount_usd": Decimal("10"),
        "frequency": DCAFrequency.DAILY,
        "dry_run": False,
    }
    defaults.update(kwargs)
    return DCAConfig(**defaults)  # type: ignore[arg-type]


def _make_order_result(
    *,
    status: OrderStatus = OrderStatus.SUCCESS,
    order_id: str | None = "test-123",
    message: str = "Order executed successfully",
) -> OrderResult:
    """テスト用 OrderResult を生成するヘルパー。"""
    return OrderResult(
        status=status,
        symbol="BTC/USDT",
        amount_usd=Decimal("10"),
        order_id=order_id,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )


class TestDCAServiceExecuteBuySuccess:
    """test_execute_buy_success: 正常に BUY 注文が成功するケース。"""

    def test_execute_buy_success(self) -> None:
        mock_exchange = MagicMock(spec=ExchangeService)
        mock_result = _make_order_result(status=OrderStatus.SUCCESS, order_id="test-123")
        mock_exchange.execute_trade.return_value = mock_result

        service = DCAService(exchange_service=mock_exchange)
        config = _make_config()
        result = service.execute(config)

        assert result.executed is True
        assert result.order_id == "test-123"
        mock_exchange.execute_trade.assert_called_once()


class TestDCAServiceExecuteDisabledSkips:
    """test_execute_disabled_skips: DCA が無効の場合、注文をスキップする。"""

    def test_execute_disabled_skips(self) -> None:
        mock_exchange = MagicMock(spec=ExchangeService)
        service = DCAService(exchange_service=mock_exchange)
        config = _make_config(enabled=False)

        result = service.execute(config)

        assert result.executed is False
        assert "disabled" in result.message.lower()
        mock_exchange.execute_trade.assert_not_called()


class TestDCAServiceExecuteDryRun:
    """test_execute_dry_run: dry_run=True の場合、SKIPPED ステータスが返る。"""

    def test_execute_dry_run(self) -> None:
        mock_exchange = MagicMock(spec=ExchangeService)
        mock_result = _make_order_result(
            status=OrderStatus.SKIPPED,
            order_id=None,
            message="dry run skipped",
        )
        mock_exchange.execute_trade.return_value = mock_result

        service = DCAService(exchange_service=mock_exchange)
        config = _make_config(dry_run=True)
        result = service.execute(config)

        assert result.executed is False


class TestDCAServiceExecuteExchangeErrorDoesNotRaise:
    """test_execute_exchange_error_does_not_raise: 例外が発生しても DCAService は例外を投げない。"""

    def test_execute_exchange_error_does_not_raise(self) -> None:
        mock_exchange = MagicMock(spec=ExchangeService)
        mock_exchange.execute_trade.side_effect = Exception("connection error")

        service = DCAService(exchange_service=mock_exchange)
        config = _make_config()

        # 例外を投げないことを確認
        result = service.execute(config)

        assert result.executed is False
        assert "failed" in result.message.lower()


class TestDCAServiceExecuteReturnsResult:
    """test_execute_returns_result: 結果に正しい symbol と amount_usd が含まれる。"""

    def test_execute_returns_result(self) -> None:
        mock_exchange = MagicMock(spec=ExchangeService)
        mock_result = _make_order_result(status=OrderStatus.SUCCESS)
        mock_exchange.execute_trade.return_value = mock_result

        service = DCAService(exchange_service=mock_exchange)
        config = _make_config(symbol="ETH/USDT", amount_usd=Decimal("50"))
        result = service.execute(config)

        assert isinstance(result, DCAExecutionResult)
        assert result.symbol == "ETH/USDT"
        assert result.amount_usd == Decimal("50")