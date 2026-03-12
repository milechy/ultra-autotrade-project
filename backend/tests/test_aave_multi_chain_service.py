# backend/tests/test_aave_multi_chain_service.py
"""
MultiChainAaveService のユニットテスト。

各チェーンが独立した Health Factor 管理を行うことを検証する。
"""

from datetime import datetime, timezone
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
from app.aave.service import AaveService, MultiChainAaveService
from app.ai.schemas import TradeAction


class FakeAaveClient:
    """テスト用フェイククライアント。"""

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
        self._is_stale_value = is_stale_value

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return self._is_stale_value


class FakeMonitoringService:
    """テスト用のモニタリングサービスモック。"""

    def __init__(self, trading_allowed: bool = True) -> None:
        self._trading_allowed = trading_allowed

    def is_trading_allowed(self) -> bool:
        return self._trading_allowed

    def record_health_factor(self, hf, at=None):
        from unittest.mock import MagicMock

        result = MagicMock()
        result.is_emergency = False
        return result


def _make_settings(chain_name: str = "arbitrum") -> AaveSettings:
    """テスト用の AaveSettings を生成する。"""
    return AaveSettings(
        network=chain_name,
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100.0"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0000000000000000000000000000000000000000",
        chain_name=chain_name,
    )


def _make_service(
    chain_name: str = "arbitrum",
    health_factor: Decimal = Decimal("2.0"),
) -> tuple[AaveService, FakeAaveClient]:
    """テスト用の AaveService + FakeAaveClient を生成する。"""
    client = FakeAaveClient(health_factor=health_factor)
    settings = _make_settings(chain_name)
    service = AaveService(
        client=client,
        settings=settings,
        monitoring_service=FakeMonitoringService(),
        state_manager=FakeStateManager(),
    )
    return service, client


class TestMultiChainAaveService:
    def test_get_chain_names(self) -> None:
        svc_arb, _ = _make_service("arbitrum")
        svc_opt, _ = _make_service("optimism")
        multi = MultiChainAaveService(services={"arbitrum": svc_arb, "optimism": svc_opt})
        names = multi.get_chain_names()
        assert set(names) == {"arbitrum", "optimism"}

    def test_get_service_known_chain(self) -> None:
        svc_arb, _ = _make_service("arbitrum")
        multi = MultiChainAaveService(services={"arbitrum": svc_arb})
        assert multi.get_service("arbitrum") is svc_arb

    def test_get_service_unknown_chain_raises_key_error(self) -> None:
        svc_arb, _ = _make_service("arbitrum")
        multi = MultiChainAaveService(services={"arbitrum": svc_arb})
        with pytest.raises(KeyError, match="base"):
            multi.get_service("base")

    def test_execute_rebalance_delegates_to_correct_chain(self) -> None:
        svc_arb, client_arb = _make_service("arbitrum")
        svc_opt, client_opt = _make_service("optimism")
        multi = MultiChainAaveService(services={"arbitrum": svc_arb, "optimism": svc_opt})

        result = multi.execute_rebalance(
            chain_name="optimism",
            action=TradeAction.BUY,
            amount=Decimal("50"),
            dry_run=True,
        )

        assert result.operation == AaveOperationType.DEPOSIT
        assert result.status == AaveOperationStatus.SUCCESS
        # arbitrum には影響しない
        assert len(client_arb.deposit_calls) == 0

    def test_get_all_health_factors(self) -> None:
        svc_arb, _ = _make_service("arbitrum", health_factor=Decimal("2.5"))
        svc_opt, _ = _make_service("optimism", health_factor=Decimal("1.8"))
        multi = MultiChainAaveService(services={"arbitrum": svc_arb, "optimism": svc_opt})

        hfs = multi.get_all_health_factors()
        assert hfs["arbitrum"] == Decimal("2.5")
        assert hfs["optimism"] == Decimal("1.8")

    def test_get_all_health_factors_handles_error(self) -> None:
        """1 チェーンの HF 取得失敗が他チェーンに影響しないことを確認。"""
        svc_arb, _ = _make_service("arbitrum", health_factor=Decimal("2.0"))
        svc_opt, client_opt = _make_service("optimism")

        # optimism の get_health_factor を例外にする
        def raise_error() -> Decimal:
            raise RuntimeError("RPC connection failed")

        client_opt.get_health_factor = raise_error  # type: ignore[assignment]

        multi = MultiChainAaveService(services={"arbitrum": svc_arb, "optimism": svc_opt})

        hfs = multi.get_all_health_factors()
        assert hfs["arbitrum"] == Decimal("2.0")
        assert hfs["optimism"] is None

    def test_independent_hf_management_chain_a_blocked_chain_b_works(self) -> None:
        """
        チェーン A の HF < 1.6 → BUY ブロック、
        チェーン B の HF >= 1.6 → BUY 通常動作。
        """
        # arbitrum: HF = 1.4 (below threshold)
        svc_arb, client_arb = _make_service("arbitrum", health_factor=Decimal("1.4"))
        # optimism: HF = 2.5 (healthy)
        svc_opt, client_opt = _make_service("optimism", health_factor=Decimal("2.5"))

        multi = MultiChainAaveService(services={"arbitrum": svc_arb, "optimism": svc_opt})

        # arbitrum の BUY はスキップされる（HF < 1.6）
        result_arb = multi.execute_rebalance(
            chain_name="arbitrum",
            action=TradeAction.BUY,
            amount=Decimal("50"),
        )
        assert result_arb.operation == AaveOperationType.NOOP
        assert result_arb.status == AaveOperationStatus.SKIPPED
        assert len(client_arb.deposit_calls) == 0

        # optimism の BUY は正常に実行される
        result_opt = multi.execute_rebalance(
            chain_name="optimism",
            action=TradeAction.BUY,
            amount=Decimal("50"),
        )
        assert result_opt.operation == AaveOperationType.DEPOSIT
        assert result_opt.status == AaveOperationStatus.SUCCESS
        assert len(client_opt.deposit_calls) == 1
