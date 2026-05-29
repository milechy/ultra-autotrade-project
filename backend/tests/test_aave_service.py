# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_service.py

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest

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
    """
    AaveService のユニットテスト用フェイククライアント。

    - deposit / withdraw 呼び出しを記録する
    - get_health_factor は任意の値を返せる
    """

    def __init__(self, health_factor: Decimal = Decimal("2.0")) -> None:
        self.health_factor = health_factor
        self.deposit_calls: list[tuple[str, Decimal]] = []
        self.withdraw_calls: list[tuple[str, Decimal]] = []

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self.health_factor

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append((asset_symbol, amount))
        return "tx-deposit"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append((asset_symbol, amount))
        return "tx-withdraw"


class FakeStateManager:
    """テスト用の state_manager モック。"""

    def __init__(
        self,
        state: Optional[AaveSystemState] = None,
        is_stale_value: bool = False,
    ) -> None:
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

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return self._is_stale


class FakeMonitoringService:
    """テスト用の monitoring_service モック。"""

    def __init__(self, trading_allowed: bool = True) -> None:
        self._trading_allowed = trading_allowed
        self._last_health_factor: Optional[Decimal] = None

    def is_trading_allowed(self) -> bool:
        return self._trading_allowed

    def record_health_factor(self, value: Optional[Decimal], *, at=None):
        """ヘルスファクターを記録（テスト用ダミー）"""
        self._last_health_factor = value

        # HealthFactorStatus の代わりにシンプルなオブジェクトを返す
        class FakeHFStatus:
            is_emergency = False

        return FakeHFStatus()


def _make_settings(
    *,
    cooldown_seconds: int = 600,
    max_single_trade_usd: str = "1000",
    min_health_factor: str = "1.6",
    warn_health_factor: str = "1.8",
) -> AaveSettings:
    return AaveSettings(
        network="sepolia",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal(max_single_trade_usd),
        min_health_factor=Decimal(min_health_factor),
        warn_health_factor=Decimal(warn_health_factor),
        trade_cooldown_seconds=cooldown_seconds,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0000000000000000000000000000000000000000",
    )


def test_buy_executes_deposit_when_safe() -> None:
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

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
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

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
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

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
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

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
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

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
    state_manager = FakeStateManager()
    service = AaveService(client=client, settings=settings, state_manager=state_manager)

    with pytest.raises(ValueError):
        service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("-1"),
            asset_symbol="USDC",
        )


# ==============================================================================
# State Mode Tests (Phase 3)
# ==============================================================================


def test_hard_stop_mode_blocks_all_operations() -> None:
    """HARD_STOP モード時は BUY/SELL ともに NOOP になること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state = AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.HARD_STOP,
        health_factor=Decimal("2.0"),
        last_update=datetime.now(timezone.utc),
        reason="test hard stop",
        circuit_closed=True,
        stale_threshold_seconds=300,
    )
    state_manager = FakeStateManager(state=state)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
    )

    # BUY
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.NOOP
    assert result_buy.status is AaveOperationStatus.SKIPPED
    assert "hard_stop" in result_buy.message.lower()
    assert client.deposit_calls == []

    # SELL
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.NOOP
    assert result_sell.status is AaveOperationStatus.SKIPPED
    assert client.withdraw_calls == []


def test_safe_mode_blocks_buy_only() -> None:
    """SAFE_MODE 時は BUY のみ NOOP、SELL は通ること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state = AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.SAFE_MODE,
        health_factor=Decimal("1.7"),
        last_update=datetime.now(timezone.utc),
        reason=None,
        circuit_closed=True,
        stale_threshold_seconds=300,
    )
    state_manager = FakeStateManager(state=state)
    monitoring = FakeMonitoringService(trading_allowed=True)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
        monitoring_service=monitoring,
    )

    # BUY は NOOP
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.NOOP
    assert "safe_mode" in result_buy.message.lower()
    assert client.deposit_calls == []

    # SELL は通る
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("5"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.WITHDRAW
    assert result_sell.status is AaveOperationStatus.SUCCESS
    assert client.withdraw_calls == [("USDC", Decimal("5"))]


def test_normal_mode_allows_all() -> None:
    """NORMAL モード時は BUY/SELL ともに動作すること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state = AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.NORMAL,
        health_factor=Decimal("2.0"),
        last_update=datetime.now(timezone.utc),
        reason=None,
        circuit_closed=True,
        stale_threshold_seconds=300,
    )
    state_manager = FakeStateManager(state=state)
    monitoring = FakeMonitoringService(trading_allowed=True)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
        monitoring_service=monitoring,
    )

    # BUY
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.DEPOSIT
    assert result_buy.status is AaveOperationStatus.SUCCESS
    assert client.deposit_calls == [("USDC", Decimal("10"))]

    # SELL（クールダウンを回避するためリセット）
    service._recent_actions = []
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("5"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.WITHDRAW
    assert result_sell.status is AaveOperationStatus.SUCCESS
    assert client.withdraw_calls == [("USDC", Decimal("5"))]


def test_stale_state_forces_noop() -> None:
    """state.json が stale の場合は NOOP になること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state_manager = FakeStateManager(is_stale_value=True)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
    )

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result.operation is AaveOperationType.NOOP
    assert result.status is AaveOperationStatus.SKIPPED
    assert "stale" in result.message.lower()
    assert client.deposit_calls == []
    assert client.withdraw_calls == []


def test_emergency_stop_in_state_blocks_all() -> None:
    """state.json の emergency_stop=True 時は BUY/SELL ともに NOOP。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state = AaveSystemState(
        emergency_stop=True,  # ← これがテスト対象
        mode=AaveOperationMode.NORMAL,  # モードは NORMAL
        health_factor=Decimal("2.0"),
        last_update=datetime.now(timezone.utc),
        reason="Manual stop by operator",
        circuit_closed=True,
        stale_threshold_seconds=300,
    )
    state_manager = FakeStateManager(state=state)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
    )

    # BUY
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.NOOP
    assert result_buy.status is AaveOperationStatus.SKIPPED
    assert "emergency_stop" in result_buy.message.lower()
    assert client.deposit_calls == []

    # SELL
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.NOOP
    assert result_sell.status is AaveOperationStatus.SKIPPED
    assert client.withdraw_calls == []


def test_circuit_open_blocks_all() -> None:
    """circuit_closed=False 時は BUY/SELL ともに NOOP。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    state = AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.NORMAL,
        health_factor=Decimal("2.0"),
        last_update=datetime.now(timezone.utc),
        reason=None,
        circuit_closed=False,  # ← nginx が開いた状態
        stale_threshold_seconds=300,
    )
    state_manager = FakeStateManager(state=state)
    service = AaveService(
        client=client,
        settings=settings,
        state_manager=state_manager,
    )

    # BUY
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.NOOP
    assert result_buy.status is AaveOperationStatus.SKIPPED
    assert "circuit_closed" in result_buy.message.lower()
    assert client.deposit_calls == []

    # SELL
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.NOOP
    assert result_sell.status is AaveOperationStatus.SKIPPED
    assert client.withdraw_calls == []


def test_parse_error_is_stale() -> None:
    """連続パースエラーが閾値を超えた場合、is_stale() が True を返す。"""
    from app.aave.state_manager import AaveStateManager, StateFileParseError

    manager = AaveStateManager()

    # 連続エラーが閾値(3)以上の場合
    manager._last_read_error = StateFileParseError("simulated parse error")
    manager._consecutive_errors = 3  # 閾値に達している
    # リトライ間隔内であることをシミュレート
    manager._last_retry_attempt = datetime.now(timezone.utc)
    assert manager.is_stale() is True

    # エラーをクリアして確認
    manager._last_read_error = None
    manager._consecutive_errors = 0
    manager._last_retry_attempt = None
    # ファイルが存在しない場合は NOT stale（初回起動）
    # 実際のファイル存在チェックは is_stale() 内で行われる


def test_missing_state_file_is_not_stale() -> None:
    """state.json が存在しない場合は NOT stale（初回起動は正常）。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    monitoring = FakeMonitoringService(trading_allowed=True)

    # ファイル不在時は is_stale()=False を返す FakeStateManager
    class InitialStateManager:
        def __init__(self):
            self._last_read_error = None

        def read_state(self):
            # ファイル不在時はデフォルト値（初回起動）
            return AaveSystemState(
                emergency_stop=False,
                mode=AaveOperationMode.NORMAL,
                health_factor=None,
                last_update=datetime.now(timezone.utc),
                reason=None,
                circuit_closed=True,
                stale_threshold_seconds=300,
            )

        def is_stale(self) -> bool:
            # ファイル不在 = NOT stale（初回起動は正常）
            return False

    service = AaveService(
        client=client,
        settings=settings,
        state_manager=InitialStateManager(),
        monitoring_service=monitoring,
    )

    # BUY は通る（stale でブロックされない）
    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result.operation is AaveOperationType.DEPOSIT
    assert result.status is AaveOperationStatus.SUCCESS
    assert client.deposit_calls == [("USDC", Decimal("10"))]


def test_transient_parse_error_recovers() -> None:
    """一時的なパースエラーから自動回復すること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    monitoring = FakeMonitoringService(trading_allowed=True)

    # 再読み取りで回復するStateManager
    class RecoveringStateManager:
        def __init__(self):
            self._last_read_error = Exception("initial error")
            self._consecutive_errors = 1  # 閾値(3)未満
            self._recovery_attempted = False

        def read_state(self):
            return AaveSystemState(
                emergency_stop=False,
                mode=AaveOperationMode.NORMAL,
                health_factor=Decimal("2.0"),
                last_update=datetime.now(timezone.utc),
                reason=None,
                circuit_closed=True,
                stale_threshold_seconds=300,
            )

        def is_stale(self) -> bool:
            # 1回目: エラーあり → 再読み取り成功をシミュレート
            if self._last_read_error is not None and not self._recovery_attempted:
                self._recovery_attempted = True
                # 再読み取り成功をシミュレート
                self._last_read_error = None
                self._consecutive_errors = 0
                return False  # タイムスタンプは新しいと仮定
            return False

    service = AaveService(
        client=client,
        settings=settings,
        state_manager=RecoveringStateManager(),
        monitoring_service=monitoring,
    )

    # 自動回復後は通常動作
    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result.operation is AaveOperationType.DEPOSIT
    assert result.status is AaveOperationStatus.SUCCESS


def test_persistent_parse_error_stays_stale() -> None:
    """連続パースエラーが閾値以上の場合は stale のまま（fail-closed）。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()

    # 連続エラーが閾値を超えているStateManager
    class PersistentErrorStateManager:
        def __init__(self):
            self._last_read_error = Exception("persistent error")
            self._consecutive_errors = 5  # 閾値(3)超過

        def read_state(self):
            return AaveSystemState(
                emergency_stop=False,
                mode=AaveOperationMode.NORMAL,
                health_factor=Decimal("2.0"),
                last_update=datetime.now(timezone.utc),
                reason=None,
                circuit_closed=True,
                stale_threshold_seconds=300,
            )

        def is_stale(self) -> bool:
            # 連続エラー >= 3 → 再読み取りせずに True
            if self._consecutive_errors >= 3:
                return True
            return False

    service = AaveService(
        client=client,
        settings=settings,
        state_manager=PersistentErrorStateManager(),
    )

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    # 永続的エラー → NOOP
    assert result.operation is AaveOperationType.NOOP
    assert result.status is AaveOperationStatus.SKIPPED
    assert "stale" in result.message.lower()


def test_file_deleted_after_error_recovers() -> None:
    """エラー後にファイルが削除されたら初期状態に戻ること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()
    monitoring = FakeMonitoringService(trading_allowed=True)

    # ファイル削除で回復するStateManager
    class DeletedFileStateManager:
        def __init__(self):
            self._last_read_error = Exception("previous error")
            self._consecutive_errors = 1
            self._recovery_attempted = False

        def read_state(self):
            # 回復後はデフォルト状態
            return AaveSystemState(
                emergency_stop=False,
                mode=AaveOperationMode.NORMAL,
                health_factor=None,
                last_update=datetime.now(timezone.utc),
                reason=None,
                circuit_closed=True,
                stale_threshold_seconds=300,
            )

        def is_stale(self) -> bool:
            # 1回目: エラーあり → ファイル不在をシミュレート（初期状態へ）
            if self._last_read_error is not None and not self._recovery_attempted:
                self._recovery_attempted = True
                # ファイルが削除されたことをシミュレート
                self._last_read_error = None
                self._consecutive_errors = 0
                return False  # 初期状態として扱う
            return False

    service = AaveService(
        client=client,
        settings=settings,
        state_manager=DeletedFileStateManager(),
        monitoring_service=monitoring,
    )

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    # 初期状態で動作
    assert result.operation is AaveOperationType.DEPOSIT
    assert result.status is AaveOperationStatus.SUCCESS


# ==============================================================================
# Safe Default Tests (Phase 4) - Fail-closed behavior on parse error
# ==============================================================================


def test_safe_default_state_values() -> None:
    """get_safe_default_state() が安全側のデフォルト値を返すこと。"""
    from app.aave.state_manager import get_safe_default_state

    state = get_safe_default_state()

    # 安全側のデフォルト値
    assert state.emergency_stop is True
    assert state.mode == AaveOperationMode.HARD_STOP
    assert state.circuit_closed is False
    assert state.health_factor is None
    assert "parse error" in state.reason.lower()


def test_normal_default_state_values() -> None:
    """get_default_state() が通常のデフォルト値を返すこと（初回起動用）。"""
    from app.aave.state_manager import get_default_state

    state = get_default_state()

    # 初回起動用のデフォルト値
    assert state.emergency_stop is False
    assert state.mode == AaveOperationMode.NORMAL
    assert state.circuit_closed is True


def test_parse_error_returns_safe_default() -> None:
    """AaveStateManager.read_state() がパースエラー時に安全側デフォルトを返すこと。"""
    import os
    import tempfile
    from pathlib import Path

    from app.aave.state_manager import AaveStateManager

    # 壊れた state.json を作成
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        state_path.write_text("{ invalid json }", encoding="utf-8")

        # 環境変数でパスを設定
        os.environ["AAVE_STATE_FILE_PATH"] = str(state_path)

        try:
            manager = AaveStateManager()
            state = manager.read_state()

            # 安全側デフォルトが返される
            assert state.emergency_stop is True
            assert state.mode == AaveOperationMode.HARD_STOP
            assert state.circuit_closed is False
            assert manager._last_read_error is not None
            assert manager._consecutive_errors == 1

        finally:
            # 環境変数をクリア
            if "AAVE_STATE_FILE_PATH" in os.environ:
                del os.environ["AAVE_STATE_FILE_PATH"]


def test_parse_error_blocks_all_operations() -> None:
    """パースエラー時の safe default により全操作がブロックされること。"""
    client = FakeAaveClient(health_factor=Decimal("2.0"))
    settings = _make_settings()

    # safe default を返す StateManager をシミュレート
    class SafeDefaultStateManager:
        def __init__(self):
            self._last_read_error = Exception("parse error")
            self._consecutive_errors = 1

        def read_state(self):
            # パースエラー時は safe default を返す
            return AaveSystemState(
                emergency_stop=True,
                mode=AaveOperationMode.HARD_STOP,
                health_factor=None,
                last_update=datetime.now(timezone.utc),
                reason="state.json parse error - fail-closed for safety",
                circuit_closed=False,
                stale_threshold_seconds=300,
            )

        def is_stale(self) -> bool:
            # パースエラーはあるが連続エラーが閾値未満なので再読み取りをシミュレート
            # ここでは stale=False として read_state() が呼ばれるケースをテスト
            return False

    service = AaveService(
        client=client,
        settings=settings,
        state_manager=SafeDefaultStateManager(),
    )

    # BUY はブロックされる（emergency_stop=True）
    result_buy = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_buy.operation is AaveOperationType.NOOP
    assert result_buy.status is AaveOperationStatus.SKIPPED
    assert "emergency_stop" in result_buy.message.lower()
    assert client.deposit_calls == []

    # SELL もブロックされる（emergency_stop=True）
    result_sell = service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )
    assert result_sell.operation is AaveOperationType.NOOP
    assert result_sell.status is AaveOperationStatus.SKIPPED
    assert client.withdraw_calls == []


def test_file_not_found_returns_normal_default() -> None:
    """state.json が存在しない場合は通常のデフォルト（運用可能状態）を返すこと。"""
    import os
    import tempfile
    from pathlib import Path

    from app.aave.state_manager import AaveStateManager

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "nonexistent_state.json"
        # ファイルは作成しない

        os.environ["AAVE_STATE_FILE_PATH"] = str(state_path)

        try:
            manager = AaveStateManager()
            state = manager.read_state()

            # 初回起動用のデフォルト値（運用可能状態）
            assert state.emergency_stop is False
            assert state.mode == AaveOperationMode.NORMAL
            assert state.circuit_closed is True
            # エラーフラグはクリア
            assert manager._last_read_error is None
            assert manager._consecutive_errors == 0

        finally:
            if "AAVE_STATE_FILE_PATH" in os.environ:
                del os.environ["AAVE_STATE_FILE_PATH"]


# ==============================================================================
# Retry Throttling Tests (Phase 4) - Rate limiting for persistent errors
# ==============================================================================


def test_retry_throttle_within_interval() -> None:
    """連続エラー閾値超過後、リトライ間隔内は再読み取りをスキップすること。"""
    from app.aave.state_manager import AaveStateManager, StateFileParseError

    manager = AaveStateManager()

    # 閾値以上の連続エラー状態を作成
    manager._last_read_error = StateFileParseError("persistent error")
    manager._consecutive_errors = 5  # >= MAX_CONSECUTIVE_ERRORS (3)

    # 最後のリトライを「今」に設定（間隔内）
    now = datetime.now(timezone.utc)
    manager._last_retry_attempt = now

    # _now() をモックして 30 秒後をシミュレート
    manager._now = lambda: now + timedelta(seconds=30)  # 60秒未満

    # is_stale() を呼ぶ → 再読み取りなしで stale
    result = manager.is_stale()

    assert result is True
    # _consecutive_errors は変わらない（再読み取りしていないため）
    assert manager._consecutive_errors == 5
    # _last_retry_attempt も更新されない
    assert manager._last_retry_attempt == now


def test_retry_throttle_after_interval_still_broken() -> None:
    """リトライ間隔経過後、再読み取りを試みるがまだ壊れている場合。"""
    import os
    import tempfile
    from pathlib import Path

    from app.aave.state_manager import AaveStateManager, StateFileParseError

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        # 壊れた state.json を作成
        state_path.write_text("{ invalid json }", encoding="utf-8")

        os.environ["AAVE_STATE_FILE_PATH"] = str(state_path)

        try:
            manager = AaveStateManager()

            # 閾値以上の連続エラー状態を作成
            manager._last_read_error = StateFileParseError("persistent error")
            manager._consecutive_errors = 5

            # 最後のリトライを 70 秒前に設定（間隔経過）
            now = datetime.now(timezone.utc)
            manager._last_retry_attempt = now - timedelta(seconds=70)

            # is_stale() を呼ぶ → 再読み取りを試みる
            result = manager.is_stale()

            assert result is True  # まだ壊れているので stale
            # _last_retry_attempt が更新されている（リトライを試みた証拠）
            assert manager._last_retry_attempt is not None
            assert manager._last_retry_attempt > now - timedelta(seconds=70)
            # エラーは維持（閾値超過後はカウントを増やさない）
            assert manager._consecutive_errors == 5

        finally:
            if "AAVE_STATE_FILE_PATH" in os.environ:
                del os.environ["AAVE_STATE_FILE_PATH"]


def test_retry_throttle_recovery_after_interval() -> None:
    """リトライ間隔経過後、ファイルが修復されていれば回復すること。"""
    import json
    import os
    import tempfile
    from pathlib import Path

    from app.aave.state_manager import AaveStateManager, StateFileParseError

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"

        # 正常な state.json を作成（mode は小文字）
        valid_state = {
            "emergency_stop": False,
            "mode": "normal",
            "health_factor": "2.0",
            "last_update": datetime.now(timezone.utc).isoformat(),
            "reason": None,
            "circuit_closed": True,
            "stale_threshold_seconds": 300,
        }
        state_path.write_text(json.dumps(valid_state), encoding="utf-8")

        os.environ["AAVE_STATE_FILE_PATH"] = str(state_path)

        try:
            manager = AaveStateManager()

            # 閾値以上の連続エラー状態を作成（過去にエラーがあった）
            manager._last_read_error = StateFileParseError("past error")
            manager._consecutive_errors = 5

            # 最後のリトライを 70 秒前に設定（間隔経過）
            now = datetime.now(timezone.utc)
            manager._last_retry_attempt = now - timedelta(seconds=70)

            # is_stale() を呼ぶ → 再読み取りを試み、成功
            result = manager.is_stale()

            assert result is False  # ファイルは新しいので NOT stale
            # エラーフラグがクリアされている（回復成功）
            assert manager._last_read_error is None
            assert manager._consecutive_errors == 0
            assert manager._last_retry_attempt is None

        finally:
            if "AAVE_STATE_FILE_PATH" in os.environ:
                del os.environ["AAVE_STATE_FILE_PATH"]


# ---------------------------------------------------------------------------
# Health Factor Infinity バリデーターのテスト
# ---------------------------------------------------------------------------


class TestHealthFactorInfinityValidators:
    """Aave V3 が返す HF=∞ を Pydantic スキーマが 999.0 に変換することを確認するテスト群。"""

    def test_aave_system_state_infinity_to_999(self):
        from decimal import Decimal

        from app.aave.schemas import AaveSystemState

        state = AaveSystemState(
            emergency_stop=False,
            mode="normal",
            health_factor=Decimal("Infinity"),
            last_update=datetime.now(timezone.utc),
            circuit_closed=True,
        )
        assert state.health_factor == Decimal("999.0")

    def test_aave_system_state_none_preserved(self):
        from app.aave.schemas import AaveSystemState

        state = AaveSystemState(
            emergency_stop=False,
            mode="normal",
            health_factor=None,
            last_update=datetime.now(timezone.utc),
            circuit_closed=True,
        )
        assert state.health_factor is None

    def test_aave_operation_result_before_after_infinity(self):
        from decimal import Decimal

        from app.aave.schemas import (
            AaveOperationResult,
            AaveOperationStatus,
            AaveOperationType,
        )

        result = AaveOperationResult(
            operation=AaveOperationType.NOOP,
            status=AaveOperationStatus.SKIPPED,
            asset_symbol="USDC",
            amount=Decimal("0"),
            before_health_factor=Decimal("Infinity"),
            after_health_factor=Decimal("Infinity"),
        )
        assert result.before_health_factor == Decimal("999.0")
        assert result.after_health_factor == Decimal("999.0")

    def test_aave_monitor_status_infinity(self):
        from decimal import Decimal

        from app.aave.schemas import AaveBalanceInfo, AaveMonitorStatus

        status = AaveMonitorStatus(
            health_factor=Decimal("Infinity"),
            balance=AaveBalanceInfo(
                wallet_address="0x1234",
                usdc_balance=Decimal("0"),
                a_usdc_balance=Decimal("0"),
            ),
            client_type="dummy",
            fetched_at="2026-01-01T00:00:00Z",
        )
        assert status.health_factor == Decimal("999.0")

    def test_health_factor_status_infinity(self):
        from decimal import Decimal

        from app.automation.schemas import AlertLevel, HealthFactorStatus

        hf_status = HealthFactorStatus(
            current=Decimal("Infinity"),
            level=AlertLevel.INFO,
            is_emergency=False,
        )
        assert hf_status.current == Decimal("999.0")

    def test_automation_status_last_hf_infinity(self):
        from decimal import Decimal

        from app.automation.schemas import AlertLevel, AutomationStatus

        status = AutomationStatus(
            is_trading_paused=False,
            last_health_factor=Decimal("Infinity"),
            last_event_level=AlertLevel.INFO,
        )
        assert status.last_health_factor == Decimal("999.0")

    def test_finite_hf_unchanged(self):
        from decimal import Decimal

        from app.automation.schemas import AlertLevel, HealthFactorStatus

        hf_status = HealthFactorStatus(
            current=Decimal("1.85"),
            level=AlertLevel.INFO,
            is_emergency=False,
        )
        assert hf_status.current == Decimal("1.85")
