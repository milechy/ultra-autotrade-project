# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_integration.py
"""
AaveService ↔ AaveClient 統合テスト。

AaveService.execute_rebalance() が正しく deposit/withdraw/NOOP を呼び分けるか検証。
全てモック — 実RPC不使用。
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.aave.config import AaveSettings
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.aave.service import AaveService
from app.ai.schemas import TradeAction


class FakeAaveClient:
    """統合テスト用フェイククライアント。"""

    def __init__(self, health_factor: Decimal = Decimal("2.0")) -> None:
        self.health_factor = health_factor
        self.deposit_calls: list = []
        self.withdraw_calls: list = []

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self.health_factor

    def deposit(self, asset_symbol: str, amount: Decimal, wallet_address: str = "") -> str:
        self.deposit_calls.append((asset_symbol, amount))
        return "tx-deposit"

    def withdraw(self, asset_symbol: str, amount: Decimal, wallet_address: str = "") -> str:
        self.withdraw_calls.append((asset_symbol, amount))
        return "tx-withdraw"


class FakeStateManager:
    def __init__(self, state=None, is_stale_value=False):
        self._state = state or AaveSystemState(
            emergency_stop=False,
            mode=AaveOperationMode.NORMAL,
            health_factor=Decimal("2.0"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=True,
            stale_threshold_seconds=300,
        )
        self._is_stale = is_stale_value

    def read_state(self):
        return self._state

    def is_stale(self):
        return self._is_stale


class FakeMonitoringService:
    def __init__(self, trading_allowed=True):
        self._trading_allowed = trading_allowed

    def is_trading_allowed(self):
        return self._trading_allowed

    def record_health_factor(self, value, *, at=None):
        class FakeHFStatus:
            is_emergency = False

        return FakeHFStatus()


def _make_settings(**kwargs):
    defaults = {
        "network": "sepolia",
        "default_asset_symbol": "USDC",
        "max_single_trade_usd": Decimal("1000"),
        "min_health_factor": Decimal("1.6"),
        "warn_health_factor": Decimal("1.8"),
        "trade_cooldown_seconds": 600,
        "rpc_url": None,
        "private_key": None,
        "operation_mode": "NORMAL",
        "state_file_path": "/tmp/test_state.json",
        "state_stale_threshold_seconds": 300,
        "pool_addresses_provider": "0x0000000000000000000000000000000000000000",
    }
    defaults.update(kwargs)
    return AaveSettings(**defaults)


def _make_service(client=None, settings=None, monitoring=None, state_manager=None):
    return AaveService(
        client=client or FakeAaveClient(),
        settings=settings or _make_settings(),
        monitoring_service=monitoring or FakeMonitoringService(),
        state_manager=state_manager or FakeStateManager(),
    )


class TestAaveIntegration:
    def test_workflow_buy_triggers_deposit(self) -> None:
        """BUY アクション → deposit() が1回呼ばれる"""
        client = FakeAaveClient(health_factor=Decimal("2.5"))
        service = _make_service(client=client)

        result = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )

        assert result.operation is AaveOperationType.DEPOSIT
        assert result.status is AaveOperationStatus.SUCCESS
        assert len(client.deposit_calls) == 1
        assert client.withdraw_calls == []

    def test_workflow_sell_triggers_withdraw(self) -> None:
        """SELL アクション → withdraw() が1回呼ばれる"""
        client = FakeAaveClient(health_factor=Decimal("2.5"))
        service = _make_service(client=client)

        result = service.execute_rebalance(
            action=TradeAction.SELL,
            amount=Decimal("5"),
            asset_symbol="USDC",
        )

        assert result.operation is AaveOperationType.WITHDRAW
        assert result.status is AaveOperationStatus.SUCCESS
        assert len(client.withdraw_calls) == 1
        assert client.deposit_calls == []

    def test_workflow_hold_triggers_noop(self) -> None:
        """HOLD → クライアント呼び出しなし"""
        client = FakeAaveClient(health_factor=Decimal("2.5"))
        service = _make_service(client=client)

        result = service.execute_rebalance(
            action=TradeAction.HOLD,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )

        assert result.operation is AaveOperationType.NOOP
        assert result.status is AaveOperationStatus.SKIPPED
        assert client.deposit_calls == []
        assert client.withdraw_calls == []

    def test_hf_below_threshold_blocks_deposit(self) -> None:
        """HF < 1.6 で BUY → deposit() は呼ばれない"""
        client = FakeAaveClient(health_factor=Decimal("1.4"))
        service = _make_service(client=client)

        result = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )

        assert result.operation is AaveOperationType.NOOP
        assert result.status is AaveOperationStatus.SKIPPED
        assert client.deposit_calls == []

    def test_cooldown_blocks_second_trade(self) -> None:
        """10分以内の2回目トレード → 2回目は NOOP"""
        client = FakeAaveClient(health_factor=Decimal("2.5"))
        service = _make_service(client=client)

        # 1回目: 成功
        result1 = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )
        assert result1.operation is AaveOperationType.DEPOSIT
        assert result1.status is AaveOperationStatus.SUCCESS

        # 2回目: クールダウンで NOOP
        result2 = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )
        assert result2.operation is AaveOperationType.NOOP
        assert result2.status is AaveOperationStatus.SKIPPED
        # deposit は1回だけ
        assert len(client.deposit_calls) == 1

    def test_dry_run_no_tx_sent(self) -> None:
        """dry_run=True → deposit()/withdraw() が tx を送信しない"""
        client = FakeAaveClient(health_factor=Decimal("2.5"))
        service = _make_service(client=client)

        result = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
            dry_run=True,
        )

        assert result.operation is AaveOperationType.DEPOSIT
        assert result.status is AaveOperationStatus.SUCCESS
        assert result.tx_hash is None
        assert "dry-run" in result.message.lower()
        # dry_run なので実際の deposit() は呼ばれない
        assert client.deposit_calls == []
