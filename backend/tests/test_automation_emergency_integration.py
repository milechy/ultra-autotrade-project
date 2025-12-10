# backend/tests/test_automation_emergency_integration.py

from decimal import Decimal

from app.ai.schemas import TradeAction
from app.aave.config import AaveSettings
from app.aave.schemas import AaveOperationStatus, AaveOperationType
from app.aave.service import AaveService
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import ComponentType
from app.automation.state import reset_state


class FakeAaveClientForEmergency:
    """
    緊急停止連携をテストするための簡易フェイククライアント。

    実際の on-chain 処理は行わない。
    """

    def __init__(self) -> None:
        self.deposit_calls: list[Decimal] = []
        self.withdraw_calls: list[Decimal] = []

    def get_health_factor(self) -> Decimal:
        # テストでは固定値を返す（MonitoringService 側で別途テスト済み）
        return Decimal("1.5")

    def deposit(self, *, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append(amount)
        return "0x-deposit"

    def withdraw(self, *, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append(amount)
        return "0x-withdraw"


def _make_settings() -> AaveSettings:
    return AaveSettings(
        network="testnet",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100"),
        min_health_factor=Decimal("1.6"),
        trade_cooldown_seconds=600,
    )


def test_execute_rebalance_respects_emergency_stop() -> None:
    """
    MonitoringService で緊急停止された場合、
    AaveService.execute_rebalance がポジションを増やさないことを確認する。
    """
    reset_state()
    monitoring = MonitoringService()
    monitoring.activate_emergency_stop(
        reason="test emergency",
        component=ComponentType.AAVE,
    )

    client = FakeAaveClientForEmergency()
    settings = _make_settings()
    service = AaveService(client=client, settings=settings, monitoring_service=monitoring)

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("10"),
        asset_symbol="USDC",
    )

    # 緊急停止中のため NOOP となり、実際の deposit は呼ばれない想定
    assert result.operation == AaveOperationType.NOOP
    assert result.status in (
        AaveOperationStatus.SUCCESS,
        AaveOperationStatus.SKIPPED,
    )
    assert client.deposit_calls == []
