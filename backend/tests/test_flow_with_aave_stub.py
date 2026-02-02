# backend/tests/test_flow_with_aave_stub.py
"""
AI → OctoBot → Aave の統合フローテスト。

シナリオ:
1. BUY シグナル (confidence=85) → OctoBot 送信成功 → Aave DEPOSIT
2. SELL シグナル (confidence=80) → OctoBot 送信成功 → Aave WITHDRAW
3. 低信頼度シグナル (confidence=50) → OctoBot スキップ → Aave NOOP
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

import pytest

from app.ai.schemas import TradeAction
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.aave.service import AaveService
from app.aave.state_manager import AaveStateManager
from app.automation.state import reset_state
from app.bots.schemas import OctoBotSignal, OctoBotSignalRequest
from app.bots.service import OctoBotService


# ---- Mock / Fake Classes ----


class MockOctoBotClient:
    """
    OctoBot 外部 API への送信をシミュレートするモッククライアント。

    send_signal に渡されたペイロードを記録するだけ。
    """

    def __init__(self) -> None:
        self.sent_payloads: List[Dict[str, Any]] = []

    def send_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.sent_payloads.append(payload)
        return {"status": "ok"}


class FakeAaveClient:
    """
    Aave クライアントのフェイク実装。

    - deposit/withdraw の呼び出しを記録
    - get_health_factor は Decimal("2.0") を固定で返す
    """

    def __init__(self) -> None:
        self.deposit_calls: List[Dict[str, Any]] = []
        self.withdraw_calls: List[Dict[str, Any]] = []

    def get_health_factor(self) -> Decimal:
        return Decimal("2.0")

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append({"asset_symbol": asset_symbol, "amount": amount})
        return f"fake-deposit-tx-{asset_symbol}-{amount}"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append({"asset_symbol": asset_symbol, "amount": amount})
        return f"fake-withdraw-tx-{asset_symbol}-{amount}"


class FakeAaveStateManager(AaveStateManager):
    """
    state.json を読み書きせず、常に正常な state を返すフェイク。
    """

    def __init__(self) -> None:
        super().__init__()

    def read_state(self) -> AaveSystemState:
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
        return False


# ---- Fixtures ----


@pytest.fixture(autouse=True)
def reset_monitoring_state() -> None:
    """各テスト前に MonitoringService の状態をリセット。"""
    reset_state()


@pytest.fixture
def mock_octobot_client() -> MockOctoBotClient:
    return MockOctoBotClient()


@pytest.fixture
def fake_aave_client() -> FakeAaveClient:
    return FakeAaveClient()


@pytest.fixture
def fake_state_manager() -> FakeAaveStateManager:
    return FakeAaveStateManager()


# ---- Test Scenarios ----


def test_scenario_buy_to_deposit(
    mock_octobot_client: MockOctoBotClient,
    fake_aave_client: FakeAaveClient,
    fake_state_manager: FakeAaveStateManager,
) -> None:
    """
    シナリオ 1: BUY → DEPOSIT

    confidence=85 の BUY シグナル
    → OctoBotService.process_signals で OctoBot へ送信
    → AaveService.execute_rebalance で DEPOSIT 実行
    """
    # 1. OctoBot シグナル処理
    octobot_service = OctoBotService(
        client=mock_octobot_client,
        min_confidence=70,
        max_same_action_per_hour=3,
    )

    signal = OctoBotSignal(
        id="test-signal-buy-001",
        url="https://example.com/news/buy",
        action=TradeAction.BUY,
        confidence=85,
        reason="Strong bullish sentiment detected",
        timestamp=datetime.now(timezone.utc),
    )

    request = OctoBotSignalRequest(signals=[signal], count=1)
    response = octobot_service.process_signals(request)

    # OctoBot 検証: success_count==1, sent_payloads に BUY がある
    assert response.success_count == 1
    assert response.skipped_count == 0
    assert response.failed_count == 0
    assert len(mock_octobot_client.sent_payloads) == 1
    assert mock_octobot_client.sent_payloads[0]["action"] == "BUY"

    # 2. Aave 処理
    aave_service = AaveService(
        client=fake_aave_client,
        state_manager=fake_state_manager,
    )

    result = aave_service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("50"),
        asset_symbol="USDC",
    )

    # Aave 検証: operation==DEPOSIT, status==SUCCESS
    assert result.operation == AaveOperationType.DEPOSIT
    assert result.status == AaveOperationStatus.SUCCESS
    assert len(fake_aave_client.deposit_calls) == 1
    assert fake_aave_client.deposit_calls[0]["asset_symbol"] == "USDC"
    assert fake_aave_client.deposit_calls[0]["amount"] == Decimal("50")
    assert len(fake_aave_client.withdraw_calls) == 0


def test_scenario_sell_to_withdraw(
    mock_octobot_client: MockOctoBotClient,
    fake_aave_client: FakeAaveClient,
    fake_state_manager: FakeAaveStateManager,
) -> None:
    """
    シナリオ 2: SELL → WITHDRAW

    confidence=80 の SELL シグナル
    → OctoBotService.process_signals で OctoBot へ送信
    → AaveService.execute_rebalance で WITHDRAW 実行
    """
    # 1. OctoBot シグナル処理
    octobot_service = OctoBotService(
        client=mock_octobot_client,
        min_confidence=70,
        max_same_action_per_hour=3,
    )

    signal = OctoBotSignal(
        id="test-signal-sell-001",
        url="https://example.com/news/sell",
        action=TradeAction.SELL,
        confidence=80,
        reason="Bearish sentiment detected",
        timestamp=datetime.now(timezone.utc),
    )

    request = OctoBotSignalRequest(signals=[signal], count=1)
    response = octobot_service.process_signals(request)

    # OctoBot 検証: success_count==1, sent_payloads に SELL がある
    assert response.success_count == 1
    assert response.skipped_count == 0
    assert response.failed_count == 0
    assert len(mock_octobot_client.sent_payloads) == 1
    assert mock_octobot_client.sent_payloads[0]["action"] == "SELL"

    # 2. Aave 処理
    aave_service = AaveService(
        client=fake_aave_client,
        state_manager=fake_state_manager,
    )

    result = aave_service.execute_rebalance(
        action=TradeAction.SELL,
        amount=Decimal("50"),
        asset_symbol="USDC",
    )

    # Aave 検証: operation==WITHDRAW, status==SUCCESS
    assert result.operation == AaveOperationType.WITHDRAW
    assert result.status == AaveOperationStatus.SUCCESS
    assert len(fake_aave_client.withdraw_calls) == 1
    assert fake_aave_client.withdraw_calls[0]["asset_symbol"] == "USDC"
    assert fake_aave_client.withdraw_calls[0]["amount"] == Decimal("50")
    assert len(fake_aave_client.deposit_calls) == 0


def test_scenario_low_confidence_skipped(
    mock_octobot_client: MockOctoBotClient,
    fake_aave_client: FakeAaveClient,
    fake_state_manager: FakeAaveStateManager,
) -> None:
    """
    シナリオ 3: 低信頼度 → SKIPPED → Aave には何も到達しない

    confidence=50（閾値 70 未満）の BUY シグナル
    → OctoBot: skipped_count==1, sent_payloads が空
    → Aave に HOLD を渡す → operation==NOOP, status==SKIPPED
    """
    # 1. OctoBot シグナル処理
    octobot_service = OctoBotService(
        client=mock_octobot_client,
        min_confidence=70,
        max_same_action_per_hour=3,
    )

    signal = OctoBotSignal(
        id="test-signal-low-conf-001",
        url="https://example.com/news/uncertain",
        action=TradeAction.BUY,
        confidence=50,  # 閾値 70 未満
        reason="Weak signal with low confidence",
        timestamp=datetime.now(timezone.utc),
    )

    request = OctoBotSignalRequest(signals=[signal], count=1)
    response = octobot_service.process_signals(request)

    # OctoBot 検証: skipped_count==1, sent_payloads が空
    assert response.success_count == 0
    assert response.skipped_count == 1
    assert response.failed_count == 0
    assert len(mock_octobot_client.sent_payloads) == 0

    # 2. Aave 処理 (HOLD を渡す)
    aave_service = AaveService(
        client=fake_aave_client,
        state_manager=fake_state_manager,
    )

    result = aave_service.execute_rebalance(
        action=TradeAction.HOLD,
        amount=Decimal("50"),
        asset_symbol="USDC",
    )

    # Aave 検証: operation==NOOP, status==SKIPPED, deposit/withdraw 両方とも空
    assert result.operation == AaveOperationType.NOOP
    assert result.status == AaveOperationStatus.SKIPPED
    assert len(fake_aave_client.deposit_calls) == 0
    assert len(fake_aave_client.withdraw_calls) == 0
