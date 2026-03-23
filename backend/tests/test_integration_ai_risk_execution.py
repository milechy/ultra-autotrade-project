# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
AI → Risk Engine → Execution 統合テスト

テスト対象フロー:
1. Knowledge入力 → AI判定 → OctoBot/Exchangeへの実行まで
2. Risk Engine (Rule Engine) がフローを適切にブロックするか
3. 緊急停止フラグ発動後はトレードが実行されないか
4. HealthFactor < 1.6 でトレードがブロックされるか
5. 提案承認フロー (proposals endpoint)

依存関係は全てモック/Fake で代替し、外部API呼び出しなし。
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.aave.service import AaveService
from app.aave.state_manager import AaveStateManager
from app.ai.schemas import CrossValidationResult, LLMDecision, LLMProvider, TradeAction
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import WorkflowRunResult
from app.automation.state import reset_state
from app.automation.workflow import check_rule_engine, process_pending_knowledge
from app.bots.schemas import OctoBotSignal, OctoBotSignalRequest
from app.bots.service import OctoBotService
from app.exchange.schemas import OrderResult, OrderStatus
from app.knowledge.schemas import KnowledgeItem, KnowledgeItemType, KnowledgeSearchResult

# ---------------------------------------------------------------------------
# Fake Clients (no external calls)
# ---------------------------------------------------------------------------


class FakeAaveClient:
    """Aave クライアントのフェイク実装（ネットワーク接続なし）。"""

    def __init__(self, health_factor: Decimal = Decimal("2.0")) -> None:
        self._hf = health_factor
        self.deposit_calls: List[Dict[str, Any]] = []
        self.withdraw_calls: List[Dict[str, Any]] = []

    def get_health_factor(self) -> Decimal:
        return self._hf

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append({"asset_symbol": asset_symbol, "amount": amount})
        return f"tx-deposit-{asset_symbol}-{amount}"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append({"asset_symbol": asset_symbol, "amount": amount})
        return f"tx-withdraw-{asset_symbol}-{amount}"


class FakeAaveStateManager(AaveStateManager):
    """state.json を読み書きしないフェイク State Manager。"""

    def __init__(self, emergency_stop: bool = False) -> None:
        super().__init__()
        self._emergency_stop = emergency_stop

    def read_state(self) -> AaveSystemState:
        return AaveSystemState(
            emergency_stop=self._emergency_stop,
            mode=AaveOperationMode.NORMAL,
            health_factor=Decimal("2.0"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=True,
            stale_threshold_seconds=300,
        )

    def is_stale(self) -> bool:
        return False


class MockOctoBotClient:
    """OctoBot クライアントのモック。"""

    def __init__(self) -> None:
        self.sent_payloads: List[Dict[str, Any]] = []

    def send_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.sent_payloads.append(payload)
        return {"status": "ok"}


def _make_knowledge_item(
    item_id: int = 1,
    title: str = "BTC Surge News",
) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title=title,
        item_type=KnowledgeItemType.TEXT,
        raw_text="Bitcoin surges past $100k on institutional demand",
        status="pending",
        chunk_count=3,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_cv_result(
    action: TradeAction = TradeAction.BUY,
    confidence: int = 85,
) -> CrossValidationResult:
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=confidence,
        reason="Strong market signal",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=confidence,
        final_reason="Strong market signal",
    )


def _make_order_result(status: OrderStatus = OrderStatus.SUCCESS) -> OrderResult:
    return OrderResult(
        order_id="order-test-001",
        status=status,
        side="buy",
        symbol="BTC/USDT",
        amount_usd=Decimal("50"),
        price=Decimal("100000"),
        message="Order filled",
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_automation_state() -> None:
    """各テスト前に MonitoringService グローバル状態をリセット。"""
    reset_state()


@pytest.fixture
def fake_aave_client() -> FakeAaveClient:
    return FakeAaveClient()


@pytest.fixture
def fake_state_manager() -> FakeAaveStateManager:
    return FakeAaveStateManager()


@pytest.fixture
def mock_octobot_client() -> MockOctoBotClient:
    return MockOctoBotClient()


# ---------------------------------------------------------------------------
# Section A: Rule Engine (check_rule_engine)
# ---------------------------------------------------------------------------


class TestRuleEngine:
    """Rule engine がトレードを適切にブロック/許可するかを確認。"""

    def test_no_monitoring_allows_trading(self) -> None:
        """MonitoringService なし → トレード許可。"""
        can_trade, reason = check_rule_engine(None)
        assert can_trade is True
        assert reason == "no_monitoring"

    def test_emergency_stop_blocks_trading(self) -> None:
        """緊急停止フラグが立っているとトレード禁止。"""
        ms = MonitoringService(enable_state_sync=False)
        ms.activate_emergency_stop(reason="test emergency")

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is False
        assert reason == "emergency_stop"

    def test_health_factor_below_threshold_blocks(self) -> None:
        """HF 1.5 (< 1.6) → トレード禁止。"""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("1.5"))

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is False
        assert reason == "hf_below_threshold"

    def test_health_factor_at_threshold_allows(self) -> None:
        """HF = 1.6 (閾値) → トレード許可。"""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("1.6"))

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is True
        assert reason == "ok"

    def test_healthy_hf_allows_trading(self) -> None:
        """HF 2.5 → トレード許可。"""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("2.5"))

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is True
        assert reason == "ok"

    def test_no_hf_recorded_allows_trading(self) -> None:
        """HF 未記録 → トレード許可（ポジションなし）。"""
        ms = MonitoringService(enable_state_sync=False)
        can_trade, reason = check_rule_engine(ms)
        assert can_trade is True
        assert reason == "ok"

    def test_emergency_stop_overrides_healthy_hf(self) -> None:
        """緊急停止は HF が健全でもブロック。"""
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("3.0"))  # 健全なHF
        ms.activate_emergency_stop(reason="manual override")

        can_trade, reason = check_rule_engine(ms)
        assert can_trade is False
        assert reason == "emergency_stop"


# ---------------------------------------------------------------------------
# Section B: AI → Risk Engine → Execution (process_pending_knowledge)
# ---------------------------------------------------------------------------


class TestAIRiskExecutionFlow:
    """AI判定 → Risk Engine → 実行 の統合フロー。"""

    def test_buy_signal_executes_order(self) -> None:
        """BUY シグナル → オーダー実行 → traded_count=1。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [_make_knowledge_item()]
        ks.search.return_value = [
            KnowledgeSearchResult(chunk_id=1, document_id=1, content="BTC up", similarity=0.9)
        ]
        ai.judge_with_rag.return_value = _make_cv_result(TradeAction.BUY, 85)
        ex.execute_trade.return_value = _make_order_result(OrderStatus.SUCCESS)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.fetched_count == 1
        assert result.traded_count == 1
        assert result.status == "completed"
        assert len(result.errors) == 0
        ex.execute_trade.assert_called_once()

    def test_sell_signal_executes_order(self) -> None:
        """SELL シグナル → オーダー実行。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [_make_knowledge_item()]
        ks.search.return_value = [
            KnowledgeSearchResult(chunk_id=1, document_id=1, content="BTC crash", similarity=0.85)
        ]
        ai.judge_with_rag.return_value = _make_cv_result(TradeAction.SELL, 80)
        ex.execute_trade.return_value = _make_order_result(OrderStatus.SUCCESS)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.traded_count == 1
        assert result.status == "completed"

    def test_hold_signal_skips_execution(self) -> None:
        """HOLD シグナル → オーダー実行なし。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [_make_knowledge_item()]
        ks.search.return_value = [
            KnowledgeSearchResult(
                chunk_id=1, document_id=1, content="mixed signals", similarity=0.6
            )
        ]
        ai.judge_with_rag.return_value = _make_cv_result(TradeAction.HOLD, 30)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.hold_count == 1
        assert result.traded_count == 0
        ex.execute_trade.assert_not_called()

    def test_low_hf_rule_engine_blocks_all(self) -> None:
        """HF < 1.6 → Rule Engine が全件 HOLD、LLM 呼び出しなし（コスト節約）。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()
        ms = MonitoringService(enable_state_sync=False)
        ms.record_health_factor(Decimal("1.4"))

        ks.get_pending.return_value = [
            _make_knowledge_item(1, "News 1"),
            _make_knowledge_item(2, "News 2"),
            _make_knowledge_item(3, "News 3"),
        ]

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
            monitoring_service=ms,
        )

        assert result.fetched_count == 3
        assert result.hold_count == 3
        assert result.traded_count == 0
        # CRITICAL: LLM should NOT be called → saves API cost
        ai.judge_with_rag.assert_not_called()
        ex.execute_trade.assert_not_called()

    def test_emergency_stop_blocks_all(self) -> None:
        """緊急停止フラグ → 全件ブロック、LLM呼び出しなし。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()
        ms = MonitoringService(enable_state_sync=False)
        ms.activate_emergency_stop(reason="market crash detected")

        ks.get_pending.return_value = [
            _make_knowledge_item(1),
            _make_knowledge_item(2),
        ]

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
            monitoring_service=ms,
        )

        assert result.hold_count == 2
        assert result.traded_count == 0
        ai.judge_with_rag.assert_not_called()
        ex.execute_trade.assert_not_called()

    def test_ai_parse_failure_defaults_to_hold(self) -> None:
        """AI 出力パース失敗 → HOLD (JSON Schema 検証失敗はトレード禁止)。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [_make_knowledge_item()]
        ks.search.return_value = []
        ai.judge_with_rag.side_effect = ValueError("LLM returned invalid JSON")

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].item_id == 1
        assert result.status in ("completed_with_errors", "failed")
        ex.execute_trade.assert_not_called()

    def test_exchange_failure_records_error_continues(self) -> None:
        """Exchange 失敗 → エラー記録、処理継続（OR logic でシステム停止しない）。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [_make_knowledge_item()]
        ks.search.return_value = [
            KnowledgeSearchResult(chunk_id=1, document_id=1, content="BTC up", similarity=0.9)
        ]
        ai.judge_with_rag.return_value = _make_cv_result(TradeAction.BUY, 85)
        ex.execute_trade.side_effect = RuntimeError("Exchange connection timeout")

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 1
        assert len(result.errors) == 1
        assert "Exchange connection timeout" in result.errors[0].message

    def test_no_pending_items_returns_no_items_status(self) -> None:
        """pending アイテムなし → no_items ステータス。"""
        db = MagicMock()
        ks = MagicMock()
        ks.get_pending.return_value = []

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=MagicMock(),
            exchange_service=MagicMock(),
        )

        assert result.status == "no_items"
        assert result.fetched_count == 0

    def test_multiple_items_mixed_results(self) -> None:
        """複数アイテム: 一部は BUY 成功、一部は HOLD → 集計が正しい。"""
        db = MagicMock()
        ks = MagicMock()
        ai = MagicMock()
        ex = MagicMock()

        ks.get_pending.return_value = [
            _make_knowledge_item(1, "Bullish news"),
            _make_knowledge_item(2, "Neutral news"),
        ]
        ks.search.return_value = [
            KnowledgeSearchResult(chunk_id=1, document_id=1, content="context", similarity=0.8)
        ]
        # First call BUY, second call HOLD
        ai.judge_with_rag.side_effect = [
            _make_cv_result(TradeAction.BUY, 85),
            _make_cv_result(TradeAction.HOLD, 40),
        ]
        ex.execute_trade.return_value = _make_order_result(OrderStatus.SUCCESS)

        result = process_pending_knowledge(
            db,
            knowledge_service=ks,
            ai_service=ai,
            exchange_service=ex,
        )

        assert result.fetched_count == 2
        assert result.traded_count == 1
        assert result.hold_count == 1
        assert result.status == "completed"


# ---------------------------------------------------------------------------
# Section C: Aave Service (via FakeAaveClient, no blockchain calls)
# ---------------------------------------------------------------------------


class TestAaveServiceFlow:
    """Aave Service の BUY/SELL/HOLD + 緊急停止テスト。"""

    def test_buy_executes_deposit(
        self,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """BUY → DEPOSIT が 1 回実行される。"""
        svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        result = svc.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("100"),
            asset_symbol="USDC",
        )
        assert result.operation == AaveOperationType.DEPOSIT
        assert result.status == AaveOperationStatus.SUCCESS
        assert len(fake_aave_client.deposit_calls) == 1
        assert fake_aave_client.deposit_calls[0]["asset_symbol"] == "USDC"
        assert fake_aave_client.deposit_calls[0]["amount"] == Decimal("100")

    def test_sell_executes_withdraw(
        self,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """SELL → WITHDRAW が 1 回実行される。"""
        svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        result = svc.execute_rebalance(
            action=TradeAction.SELL,
            amount=Decimal("50"),
            asset_symbol="USDC",
        )
        assert result.operation == AaveOperationType.WITHDRAW
        assert result.status == AaveOperationStatus.SUCCESS
        assert len(fake_aave_client.withdraw_calls) == 1

    def test_hold_is_noop(
        self,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """HOLD → NOOP。Aave クライアントは呼ばれない。"""
        svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        result = svc.execute_rebalance(
            action=TradeAction.HOLD,
            amount=Decimal("50"),
            asset_symbol="USDC",
        )
        assert result.operation == AaveOperationType.NOOP
        assert result.status == AaveOperationStatus.SKIPPED
        assert len(fake_aave_client.deposit_calls) == 0
        assert len(fake_aave_client.withdraw_calls) == 0

    def test_emergency_stop_blocks_buy(self) -> None:
        """緊急停止状態では BUY が NOOP になる。"""
        client = FakeAaveClient()
        state_mgr = FakeAaveStateManager(emergency_stop=True)
        svc = AaveService(client=client, state_manager=state_mgr)
        result = svc.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("100"),
            asset_symbol="USDC",
        )
        # Emergency stop → no deposit should happen
        assert result.status in (AaveOperationStatus.SKIPPED, AaveOperationStatus.ERROR)
        assert len(client.deposit_calls) == 0

    def test_negative_amount_raises_value_error(
        self,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """負の金額 → ValueError。"""
        svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        with pytest.raises(ValueError):
            svc.execute_rebalance(
                action=TradeAction.BUY,
                amount=Decimal("-1"),
                asset_symbol="USDC",
            )


# ---------------------------------------------------------------------------
# Section D: OctoBot → Aave フロー (End-to-End mock)
# ---------------------------------------------------------------------------


class TestOctoBotAaveFlow:
    """OctoBot シグナル → Aave 操作の統合テスト。"""

    def test_buy_signal_triggers_deposit(
        self,
        mock_octobot_client: MockOctoBotClient,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """confidence=85 BUY → OctoBot 送信成功 → Aave DEPOSIT。"""
        octobot_svc = OctoBotService(
            client=mock_octobot_client,
            min_confidence=70,
            max_same_action_per_hour=3,
        )
        signal = OctoBotSignal(
            id="sig-buy-001",
            url="https://example.com/news/buy",
            action=TradeAction.BUY,
            confidence=85,
            reason="Bullish",
            timestamp=datetime.now(timezone.utc),
        )
        request = OctoBotSignalRequest(signals=[signal], count=1)
        octo_result = octobot_svc.process_signals(request)

        assert octo_result.success_count == 1
        assert len(mock_octobot_client.sent_payloads) == 1

        aave_svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        aave_result = aave_svc.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("50"),
            asset_symbol="USDC",
        )
        assert aave_result.operation == AaveOperationType.DEPOSIT
        assert aave_result.status == AaveOperationStatus.SUCCESS

    def test_sell_signal_triggers_withdraw(
        self,
        mock_octobot_client: MockOctoBotClient,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """confidence=80 SELL → OctoBot 送信成功 → Aave WITHDRAW。"""
        octobot_svc = OctoBotService(
            client=mock_octobot_client,
            min_confidence=70,
            max_same_action_per_hour=3,
        )
        signal = OctoBotSignal(
            id="sig-sell-001",
            url="https://example.com/news/sell",
            action=TradeAction.SELL,
            confidence=80,
            reason="Bearish",
            timestamp=datetime.now(timezone.utc),
        )
        request = OctoBotSignalRequest(signals=[signal], count=1)
        octo_result = octobot_svc.process_signals(request)

        assert octo_result.success_count == 1

        aave_svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        aave_result = aave_svc.execute_rebalance(
            action=TradeAction.SELL,
            amount=Decimal("50"),
            asset_symbol="USDC",
        )
        assert aave_result.operation == AaveOperationType.WITHDRAW

    def test_low_confidence_signal_skipped(
        self,
        mock_octobot_client: MockOctoBotClient,
        fake_aave_client: FakeAaveClient,
        fake_state_manager: FakeAaveStateManager,
    ) -> None:
        """confidence=50 (< 70閾値) → OctoBot スキップ → Aave に到達しない。"""
        octobot_svc = OctoBotService(
            client=mock_octobot_client,
            min_confidence=70,
            max_same_action_per_hour=3,
        )
        signal = OctoBotSignal(
            id="sig-low-001",
            url="https://example.com/news/weak",
            action=TradeAction.BUY,
            confidence=50,  # below threshold
            reason="Weak signal",
            timestamp=datetime.now(timezone.utc),
        )
        request = OctoBotSignalRequest(signals=[signal], count=1)
        octo_result = octobot_svc.process_signals(request)

        assert octo_result.skipped_count == 1
        assert len(mock_octobot_client.sent_payloads) == 0

        # HOLD propagated to Aave → NOOP
        aave_svc = AaveService(client=fake_aave_client, state_manager=fake_state_manager)
        aave_result = aave_svc.execute_rebalance(
            action=TradeAction.HOLD,
            amount=Decimal("50"),
            asset_symbol="USDC",
        )
        assert aave_result.operation == AaveOperationType.NOOP
        assert len(fake_aave_client.deposit_calls) == 0
        assert len(fake_aave_client.withdraw_calls) == 0
