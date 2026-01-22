# backend/tests/test_aave_service.py

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.ai.schemas import TradeAction
from app.aave.config import AaveSettings
from app.aave.schemas import AaveOperationStatus, AaveOperationType
from app.aave.service import AaveService


class FakeAaveClient:
    """
    AaveService のユニットテスト用フェイククライアント。

    - deposit / withdraw 呼び出しを記録する
    - get_health_factor は任意の値を返せる
    """

    def __init__(self, health_factor: Decimal = Decimal("2.0")) -> None:
        self.health_factor = health_factor
        self.deposit_calls: list[tuple[str, Decimal]] = []
        self.withdraw_calls: list[tuple[str, Decimal]] = []

    def get_health_factor(self) -> Decimal:
        return self.health_factor

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append((asset_symbol, amount))
        return "tx-deposit"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append((asset_symbol, amount))
        return "tx-withdraw"


def _make_settings(
    *,
    cooldown_seconds: int = 600,
    max_single_trade_usd: str = "1000",
    min_health_factor: str = "1.6",
) -> AaveSettings:
    return AaveSettings(
        network="sepolia",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal(max_single_trade_usd),
        min_health_factor=Decimal(min_health_factor),
        trade_cooldown_seconds=cooldown_seconds,
    )


def test_buy_executes_deposit_when_safe() -> None:
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    service = AaveService(client=client, settings=settings)

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )

    assert result.operation is AaveOperationType.DEPOSIT
    assert result.status is AaveOperationStatus.SUCCESS
    assert client.deposit_calls == [("USDC", Decimal("10"))]
    assert client.withdraw_calls == []


def test_sell_executes_withdraw() -> None:
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    service = AaveService(client=client, settings=settings)

    result = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("5"),
        asset_symbol="USDC",
    )

    assert result.operation is AaveOperationType.WITHDRAW
    assert result.status is AaveOperationStatus.SUCCESS
    assert client.withdraw_calls == [("USDC", Decimal("5"))]
    assert client.deposit_calls == []


def test_hold_results_in_noop() -> None:
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    service = AaveService(client=client, settings=settings)

    result = service.execute_rebalance(
        action=TradeAction.HOLD,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )

    assert result.operation is AaveOperationType.NOOP
    assert result.status is AaveOperationStatus.SKIPPED
    assert client.deposit_calls == []
    assert client.withdraw_calls == []


def test_health_factor_below_threshold_skips_buy() -> None:
    # ヘルスファクターがしきい値未満のときは BUY を NOOP にする
    client = FakeAaveClient(health_factor=Decimal("1.0"))
    settings = _make_settings(min_health_factor="1.6")
    service = AaveService(client=client, settings=settings)

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )

    assert result.operation is AaveOperationType.NOOP
    assert result.status is AaveOperationStatus.SKIPPED
    assert client.deposit_calls == []
    assert client.withdraw_calls == []


def test_cooldown_skips_second_trade() -> None:
    client = FakeAaveClient()
    # クールダウン 600 秒（デフォルト）
    settings = _make_settings(cooldown_seconds=600)
    service = AaveService(client=client, settings=settings)

    # 直近にトレードがあったことにする
    service._recent_actions = [datetime.now(timezone.utc)]

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )

    assert result.operation is AaveOperationType.NOOP
    assert result.status is AaveOperationStatus.SKIPPED
    assert client.deposit_calls == []
    assert client.withdraw_calls == []


def test_negative_amount_raises_value_error() -> None:
    client = FakeAaveClient()
    settings = _make_settings()
    service = AaveService(client=client, settings=settings)

    with pytest.raises(ValueError):
        service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("-1"),
            asset_symbol="USDC",
        )
