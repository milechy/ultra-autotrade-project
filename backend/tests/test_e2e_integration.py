# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_e2e_integration.py
"""Wave 3 E2E 統合テスト: Shadow Mode / 緊急停止 / HF / 取引所切り替え / プロンプトバージョン"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.ai.schemas import (
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.ai.service import AIService
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import WorkflowRunResult
from app.automation.shadow_mode_service import ShadowModeService
from app.automation.workflow import process_pending_knowledge
from app.exchange.client import DummyExchangeClient
from app.exchange.service import ExchangeService
from app.knowledge.schemas import (
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
    KnowledgeSearchResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(item_id=1, title="BTC News"):
    return KnowledgeItem(
        id=item_id,
        source_url=None,
        title=title,
        raw_text="Bitcoin surges",
        status=KnowledgeItemStatus.PENDING,
        chunk_count=3,
        item_type=KnowledgeItemType.TEXT,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_search_results():
    return [
        KnowledgeSearchResult(
            chunk_id=1,
            document_id=1,
            content="Bitcoin hits all-time high",
            similarity=0.95,
            source_url=None,
            title="BTC News",
        )
    ]


def _make_cross_result(action=TradeAction.BUY, confidence=85, agreed=True, prompt_version="v1"):
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE, action=action, confidence=confidence, reason="test"
    )
    result = CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=agreed,
        final_action=action,
        final_confidence=confidence,
        final_reason="test reason",
    )
    result.prompt_version = prompt_version
    return result


def _make_exchange_settings():
    settings = MagicMock()
    settings.default_symbol = "BTC/USDT"
    settings.max_order_usd = Decimal("100")
    settings.daily_trade_limit = 10
    settings.cooldown_seconds = 0
    settings.sandbox = True
    return settings


def _make_db_and_ks(items=None, search_results=None):
    mock_db = MagicMock()
    mock_ks = MagicMock()
    mock_ks.get_pending.return_value = items if items is not None else [_make_item()]
    mock_ks.search.return_value = (
        search_results if search_results is not None else _make_search_results()
    )
    return mock_db, mock_ks


# ---------------------------------------------------------------------------
# Shadow Mode テスト
# ---------------------------------------------------------------------------


class TestShadowMode:
    def test_shadow_mode_on_records_and_skips_trade(self):
        """Shadow Mode ON: record()が呼ばれ、実トレードは実行されない。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        shadow_svc = MagicMock(spec=ShadowModeService)
        shadow_svc.is_enabled.return_value = True

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=shadow_svc,
        )

        assert isinstance(result, WorkflowRunResult)
        assert result.shadow_logged_count == 1
        assert result.traded_count == 0
        assert len(client.orders) == 0
        shadow_svc.record.assert_called_once()

    def test_shadow_mode_disabled_trades_normally(self):
        """Shadow Mode OFF: 通常通りトレードが実行される。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        shadow_svc = MagicMock(spec=ShadowModeService)
        shadow_svc.is_enabled.return_value = False

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=shadow_svc,
        )

        assert result.traded_count == 1
        assert result.shadow_logged_count == 0
        shadow_svc.record.assert_not_called()

    def test_shadow_mode_none_trades_normally(self):
        """shadow_mode_service=None: 通常通りトレードが実行される。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=None,
        )

        assert result.traded_count == 1
        assert result.shadow_logged_count == 0

    def test_shadow_mode_multiple_items(self):
        """Shadow Mode ON: 複数アイテム全てが記録される。"""
        mock_db, mock_ks = _make_db_and_ks(items=[_make_item(1), _make_item(2), _make_item(3)])

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        shadow_svc = MagicMock(spec=ShadowModeService)
        shadow_svc.is_enabled.return_value = True

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=shadow_svc,
        )

        assert result.shadow_logged_count == 3
        assert result.traded_count == 0
        assert shadow_svc.record.call_count == 3


# ---------------------------------------------------------------------------
# 緊急停止 / HF テスト
# ---------------------------------------------------------------------------


class TestEmergencyStopAndHF:
    def test_emergency_stop_blocks_all_items(self):
        """緊急停止: is_trading_allowed()=False → 全アイテムHOLD。"""
        mock_db, mock_ks = _make_db_and_ks(items=[_make_item(1), _make_item(2)])

        mock_ai = MagicMock(spec=AIService)
        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        monitoring = MagicMock(spec=MonitoringService)
        monitoring.get_status.return_value = MagicMock(last_health_factor=None)
        monitoring.is_trading_allowed.return_value = False

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            monitoring_service=monitoring,
        )

        assert result.fetched_count == 2
        assert result.hold_count == 2
        assert result.traded_count == 0
        mock_ai.judge_with_rag.assert_not_called()

    def test_hf_below_threshold_hard_stop(self):
        """HF < 1.6: HARD_STOP → 全アイテムHOLD、LLM呼び出しなし。"""
        mock_db, mock_ks = _make_db_and_ks(items=[_make_item(1), _make_item(2)])

        mock_ai = MagicMock(spec=AIService)
        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        monitoring = MagicMock(spec=MonitoringService)
        monitoring.get_status.return_value = MagicMock(last_health_factor=Decimal("1.5"))
        monitoring.is_trading_allowed.return_value = True  # HFチェックが先

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            monitoring_service=monitoring,
        )

        assert result.hold_count == 2
        assert result.traded_count == 0
        mock_ai.judge_with_rag.assert_not_called()

    def test_hf_at_threshold_allows_trade(self):
        """HF = 1.6: 閾値ちょうどは通過する（< 1.6 が条件）。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 85)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        monitoring = MagicMock(spec=MonitoringService)
        monitoring.get_status.return_value = MagicMock(last_health_factor=Decimal("1.6"))
        monitoring.is_trading_allowed.return_value = True

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            monitoring_service=monitoring,
        )

        assert result.traded_count == 1


# ---------------------------------------------------------------------------
# エラー率監視 テスト
# ---------------------------------------------------------------------------


class TestMonitoringRecordError:
    def test_record_error_called_on_item_exception(self):
        """アイテム処理例外時に monitoring_service.record_error() が呼ばれる。"""
        mock_db, mock_ks = _make_db_and_ks()
        mock_ks.search.side_effect = Exception("DB connection failed")

        mock_ai = MagicMock(spec=AIService)
        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        monitoring = MagicMock(spec=MonitoringService)
        monitoring.get_status.return_value = MagicMock(last_health_factor=None)
        monitoring.is_trading_allowed.return_value = True

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            monitoring_service=monitoring,
        )

        assert len(result.errors) == 1
        monitoring.record_error.assert_called_once()

    def test_record_error_not_called_on_success(self):
        """正常処理では record_error() は呼ばれない。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.HOLD, 50)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        monitoring = MagicMock(spec=MonitoringService)
        monitoring.get_status.return_value = MagicMock(last_health_factor=None)
        monitoring.is_trading_allowed.return_value = True

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            monitoring_service=monitoring,
        )

        assert result.status == "completed"
        monitoring.record_error.assert_not_called()


# ---------------------------------------------------------------------------
# 取引所切り替えテスト
# ---------------------------------------------------------------------------


class TestExchangeClientSwitch:
    def test_dummy_client_processes_order(self):
        """DummyExchangeClient: 注文がorders[]に記録される。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.BUY, 80)

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert result.traded_count == 1
        assert len(client.orders) == 1
        assert client.orders[0]["side"] in ("buy", "sell")

    def test_exchange_service_with_mock_client(self):
        """モッククライアント: create_market_order()が呼ばれる。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        mock_ai.judge_with_rag.return_value = _make_cross_result(TradeAction.SELL, 75)

        mock_client = MagicMock()
        mock_client.fetch_ticker.return_value = {"last": "50000"}
        mock_client.create_market_order.return_value = {"id": "mock-order-001"}
        exchange = ExchangeService(client=mock_client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
        )

        assert result.traded_count == 1
        mock_client.create_market_order.assert_called_once()


# ---------------------------------------------------------------------------
# プロンプトバージョン切り替えテスト
# ---------------------------------------------------------------------------


class TestPromptVersionSwitch:
    def test_prompt_version_v1_propagated(self):
        """prompt_version='v1' が CrossValidationResult に正しく設定される。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        cross_result = _make_cross_result(TradeAction.BUY, 85, prompt_version="v1")
        mock_ai.judge_with_rag.return_value = cross_result

        shadow_svc = MagicMock(spec=ShadowModeService)
        shadow_svc.is_enabled.return_value = True

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=shadow_svc,
        )

        assert result.shadow_logged_count == 1
        # record()に渡されたresultのprompt_versionを検証
        recorded_result = shadow_svc.record.call_args[0][0]
        assert recorded_result.prompt_version == "v1"

    def test_prompt_version_v2_propagated(self):
        """prompt_version='v2' が CrossValidationResult に正しく設定される。"""
        mock_db, mock_ks = _make_db_and_ks()

        mock_ai = MagicMock(spec=AIService)
        cross_result = _make_cross_result(TradeAction.HOLD, 60, prompt_version="v2")
        mock_ai.judge_with_rag.return_value = cross_result

        shadow_svc = MagicMock(spec=ShadowModeService)
        shadow_svc.is_enabled.return_value = True

        client = DummyExchangeClient()
        exchange = ExchangeService(client=client, settings=_make_exchange_settings())

        process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_ai,
            exchange_service=exchange,
            shadow_mode_service=shadow_svc,
        )

        recorded_result = shadow_svc.record.call_args[0][0]
        assert recorded_result.prompt_version == "v2"