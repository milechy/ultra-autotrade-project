# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for Codex P0 fail-closed safety fixes.

Covers:
- MacroSafeMode exception → fail-closed (all items SKIPPED)
- oracle_checker RPC failure → fail-closed (is_oracle_fresh returns False)
- reserve_monitor RPC failure → fail-closed (is_reserve_healthy returns False)
- check_rule_engine wires oracle/reserve checks
- Normal happy-path: oracle fresh + reserve active → trade allowed
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.automation.workflow import check_rule_engine, process_pending_knowledge
from app.knowledge.schemas import KnowledgeItem, KnowledgeItemStatus, KnowledgeItemType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(item_id: int = 1) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title="BTC News",
        item_type=KnowledgeItemType.TEXT,
        raw_text="Bitcoin surges",
        status="pending",
        chunk_count=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_knowledge_service(items: list) -> MagicMock:
    svc = MagicMock()
    svc.get_pending.return_value = items
    svc.search.return_value = []
    svc.update_status.return_value = None
    return svc


def _make_monitoring_service(
    *,
    hf: Decimal = Decimal("2.0"),
    trading_allowed: bool = True,
) -> MagicMock:
    svc = MagicMock()
    status = MagicMock()
    status.last_health_factor = hf
    svc.get_status.return_value = status
    svc.is_trading_allowed.return_value = trading_allowed
    return svc


# ---------------------------------------------------------------------------
# MacroSafeMode fail-closed
# ---------------------------------------------------------------------------


class TestMacroSafeModeFailClosed:
    """MacroSafeMode exception must block all trades (fail-closed)."""

    def test_exception_blocks_all_items(self) -> None:
        """When MacroSafeMode raises, all items are SKIPPED, AI judge never called."""
        from app.ai.schemas import CrossValidationResult, LLMDecision, LLMProvider, TradeAction
        from app.exchange.schemas import OrderResult, OrderStatus

        items = [_make_item(1), _make_item(2)]
        knowledge_svc = _make_knowledge_service(items)

        ai_svc = MagicMock()
        cross = CrossValidationResult(
            primary=LLMDecision(
                provider=LLMProvider.CLAUDE,
                action=TradeAction.HOLD,
                confidence=60,
                reason="test",
            ),
            secondary=None,
            agreed=True,
            final_action=TradeAction.HOLD,
            final_confidence=60,
            final_reason="test",
        )
        ai_svc.judge_with_rag.return_value = cross

        exchange_svc = MagicMock()
        exchange_svc.execute_trade.return_value = OrderResult(
            order_id="x",
            status=OrderStatus.SUCCESS,
            side="buy",
            symbol="BTC/USDT",
            amount_usd=Decimal("50"),
            price=Decimal("100000"),
            message="ok",
            timestamp=datetime.now(timezone.utc),
        )
        db = MagicMock()

        # oracle/reserve env not set → skip those checks
        with (
            patch("app.automation.macro_safe_mode.MacroSafeMode", side_effect=RuntimeError("boom")),
            patch.dict("os.environ", {}, clear=False),
        ):
            result = process_pending_knowledge(
                db,
                knowledge_service=knowledge_svc,
                ai_service=ai_svc,
                exchange_service=exchange_svc,
            )

        # fail-closed: AI must not be called
        ai_svc.judge_with_rag.assert_not_called()
        assert result.fetched_count == 2
        assert result.hold_count == 2
        assert result.traded_count == 0
        assert result.status == "completed"
        # All items skipped
        assert knowledge_svc.update_status.call_count == 2
        statuses = [c.args[2] for c in knowledge_svc.update_status.call_args_list]
        assert all(s == KnowledgeItemStatus.SKIPPED for s in statuses)


# ---------------------------------------------------------------------------
# oracle_checker fail-closed
# ---------------------------------------------------------------------------


class TestOracleCheckerFailClosed:
    """is_oracle_fresh() must return False on RPC failure (fail-closed)."""

    def test_rpc_failure_returns_false(self) -> None:
        from app.aave.oracle_checker import is_oracle_fresh

        with patch(
            "app.aave.oracle_checker.check_oracle_staleness",
            side_effect=Exception("RPC timeout"),
        ):
            result = is_oracle_fresh(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_none_result_returns_false(self) -> None:
        """check_oracle_staleness returning None (web3 unavailable) → fail-closed."""
        from app.aave.oracle_checker import is_oracle_fresh

        with patch(
            "app.aave.oracle_checker.check_oracle_staleness",
            return_value=None,
        ):
            result = is_oracle_fresh(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_stale_oracle_returns_false(self) -> None:
        """Stale oracle (should_hold=True) → is_oracle_fresh returns False."""
        from app.aave.oracle_checker import OracleCheckResult, is_oracle_fresh

        stale_result = OracleCheckResult(
            feed_address="0xFEED",
            is_stale=True,
            is_circuit_breaker=False,
            updated_at=None,
            price=None,
            age_seconds=7200,
            deviation_pct=None,
            should_hold=True,
            reasons=["oracle price is stale: age=7200s > threshold=3600s"],
        )
        with patch(
            "app.aave.oracle_checker.check_oracle_staleness",
            return_value=stale_result,
        ):
            result = is_oracle_fresh(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_fresh_oracle_returns_true(self) -> None:
        """Fresh oracle (should_hold=False) → is_oracle_fresh returns True."""
        from app.aave.oracle_checker import OracleCheckResult, is_oracle_fresh

        fresh_result = OracleCheckResult(
            feed_address="0xFEED",
            is_stale=False,
            is_circuit_breaker=False,
            updated_at=datetime.now(timezone.utc),
            price=Decimal("50000"),
            age_seconds=60,
            deviation_pct=None,
            should_hold=False,
            reasons=[],
        )
        with patch(
            "app.aave.oracle_checker.check_oracle_staleness",
            return_value=fresh_result,
        ):
            result = is_oracle_fresh(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is True

    def test_env_not_configured_returns_true(self) -> None:
        """If AAVE_ORACLE_FEED_ADDRESS not set, check is skipped (returns True)."""
        from app.aave.oracle_checker import is_oracle_fresh

        with patch.dict(
            "os.environ",
            {"AAVE_ORACLE_FEED_ADDRESS": "", "WEB3_RPC_URL": "", "POLYGON_RPC_URL": ""},
        ):
            result = is_oracle_fresh()
        assert result is True


# ---------------------------------------------------------------------------
# reserve_monitor fail-closed
# ---------------------------------------------------------------------------


class TestReserveMonitorFailClosed:
    """is_reserve_healthy() must return False on RPC failure (fail-closed)."""

    def test_rpc_failure_returns_false(self) -> None:
        from app.aave.reserve_monitor import is_reserve_healthy

        with patch(
            "app.aave.reserve_monitor.check_reserve_status",
            side_effect=Exception("RPC timeout"),
        ):
            result = is_reserve_healthy(
                chain_name="polygon",
                asset_address="0xASSET",
                data_provider_address="0xPROVIDER",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_none_result_returns_false(self) -> None:
        """check_reserve_status returning None (web3 unavailable) → fail-closed."""
        from app.aave.reserve_monitor import is_reserve_healthy

        with patch(
            "app.aave.reserve_monitor.check_reserve_status",
            return_value=None,
        ):
            result = is_reserve_healthy(
                chain_name="polygon",
                asset_address="0xASSET",
                data_provider_address="0xPROVIDER",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_paused_reserve_returns_false(self) -> None:
        """Paused reserve (alert=True) → is_reserve_healthy returns False."""
        from app.aave.reserve_monitor import ReserveStatus, is_reserve_healthy

        paused = ReserveStatus(
            chain_name="polygon",
            asset_address="0xASSET",
            is_active=True,
            is_frozen=False,
            is_paused=True,
            borrow_cap=0,
            supply_cap=0,
            is_borrowing_enabled=False,
            alert=True,
            alert_reasons=["reserve is PAUSED"],
        )
        with patch(
            "app.aave.reserve_monitor.check_reserve_status",
            return_value=paused,
        ):
            result = is_reserve_healthy(
                chain_name="polygon",
                asset_address="0xASSET",
                data_provider_address="0xPROVIDER",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_healthy_reserve_returns_true(self) -> None:
        """Active reserve (alert=False) → is_reserve_healthy returns True."""
        from app.aave.reserve_monitor import ReserveStatus, is_reserve_healthy

        healthy = ReserveStatus(
            chain_name="polygon",
            asset_address="0xASSET",
            is_active=True,
            is_frozen=False,
            is_paused=False,
            borrow_cap=0,
            supply_cap=0,
            is_borrowing_enabled=True,
            alert=False,
            alert_reasons=[],
        )
        with patch(
            "app.aave.reserve_monitor.check_reserve_status",
            return_value=healthy,
        ):
            result = is_reserve_healthy(
                chain_name="polygon",
                asset_address="0xASSET",
                data_provider_address="0xPROVIDER",
                rpc_url="http://localhost:8545",
            )
        assert result is True

    def test_env_not_configured_returns_true(self) -> None:
        """If AAVE_ASSET_ADDRESS not set, check is skipped (returns True)."""
        from app.aave.reserve_monitor import is_reserve_healthy

        with patch.dict(
            "os.environ",
            {
                "AAVE_ASSET_ADDRESS": "",
                "AAVE_DATA_PROVIDER_ADDRESS": "",
                "WEB3_RPC_URL": "",
                "POLYGON_RPC_URL": "",
            },
        ):
            result = is_reserve_healthy()
        assert result is True


# ---------------------------------------------------------------------------
# check_rule_engine oracle/reserve wiring
# ---------------------------------------------------------------------------


class TestCheckRuleEngineWiring:
    """check_rule_engine must wire oracle/reserve checks."""

    def _make_monitoring(self) -> MagicMock:
        return _make_monitoring_service()

    def test_oracle_stale_blocks_trade(self) -> None:
        """is_oracle_fresh() returning False → check_rule_engine returns (False, 'oracle_stale')."""
        monitoring = self._make_monitoring()

        with patch("app.aave.oracle_checker.is_oracle_fresh", return_value=False):
            can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is False
        assert reason == "oracle_stale"

    def test_oracle_check_exception_blocks_trade(self) -> None:
        """is_oracle_fresh() raising → check_rule_engine returns (False, 'oracle_check_failed')."""
        monitoring = self._make_monitoring()

        with patch(
            "app.aave.oracle_checker.is_oracle_fresh",
            side_effect=ImportError("no module"),
        ):
            can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is False
        assert reason == "oracle_check_failed"

    def test_reserve_paused_blocks_trade(self) -> None:
        """is_reserve_healthy() returning False → check_rule_engine returns (False, 'reserve_paused_or_frozen')."""
        monitoring = self._make_monitoring()

        with (
            patch("app.aave.oracle_checker.is_oracle_fresh", return_value=True),
            patch("app.aave.reserve_monitor.is_reserve_healthy", return_value=False),
        ):
            can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is False
        assert reason == "reserve_paused_or_frozen"

    def test_reserve_check_exception_blocks_trade(self) -> None:
        """is_reserve_healthy() raising → check_rule_engine returns (False, 'reserve_check_failed')."""
        monitoring = self._make_monitoring()

        with (
            patch("app.aave.oracle_checker.is_oracle_fresh", return_value=True),
            patch(
                "app.aave.reserve_monitor.is_reserve_healthy",
                side_effect=RuntimeError("rpc down"),
            ),
        ):
            can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is False
        assert reason == "reserve_check_failed"

    def test_oracle_fresh_reserve_healthy_allows_trade(self) -> None:
        """oracle fresh + reserve healthy → check_rule_engine returns (True, 'ok')."""
        monitoring = self._make_monitoring()

        with (
            patch("app.aave.oracle_checker.is_oracle_fresh", return_value=True),
            patch("app.aave.reserve_monitor.is_reserve_healthy", return_value=True),
        ):
            can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is True
        assert reason == "ok"

    def test_no_monitoring_skips_checks(self) -> None:
        """monitoring_service=None → oracle/reserve checks not reached, returns (True, 'no_monitoring')."""
        can_trade, reason = check_rule_engine(None)
        assert can_trade is True
        assert reason == "no_monitoring"
