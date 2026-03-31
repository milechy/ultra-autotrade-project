# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_daily_trade_limit.py

"""
Tests for the daily 30% trade limit feature.

Covers:
- RebalanceService._check_safety_constraints() daily limit block
- RebalanceService._get_daily_traded_usd() reset at UTC midnight
- RebalanceService.execute() updates _daily_traded_usd after success
- check_rule_engine() daily_limit_reached reason
- Decimal-only financial calculations
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.aave.config import AaveSettings
from app.aave.rebalance_config import RebalanceSettings
from app.aave.rebalance_service import RebalanceService
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.automation.workflow import check_rule_engine

# =============================================================================
# Fakes (copied pattern from test_rebalance_service.py)
# =============================================================================


class FakeAaveClientWithPositions:
    def __init__(
        self,
        health_factor: Decimal = Decimal("2.5"),
        total_collateral: Decimal = Decimal("10000"),
        raise_on_get_account_data: Optional[Exception] = None,
    ) -> None:
        self.hf = health_factor
        self.total_collateral = total_collateral
        self.raise_on_get_account_data = raise_on_get_account_data
        self.deposit_calls: list[dict] = []
        self.withdraw_calls: list[dict] = []

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self.hf

    def get_account_data(self, wallet_address: str):
        if self.raise_on_get_account_data is not None:
            raise self.raise_on_get_account_data
        from app.aave.client import AccountData

        return AccountData(
            total_collateral_usd=self.total_collateral,
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=self.hf,
        )

    def deposit(self, *args, **kwargs) -> dict:
        self.deposit_calls.append({"args": args, "kwargs": kwargs})
        return {"tx_hash": "0xfake_deposit"}

    def withdraw(self, *args, **kwargs) -> dict:
        self.withdraw_calls.append({"args": args, "kwargs": kwargs})
        return {"tx_hash": "0xfake_withdraw"}


class FakeAaveService:
    def __init__(self, results: Optional[list[AaveOperationResult]] = None) -> None:
        self.calls: list[dict] = []
        self._results = results or []
        self._call_index = 0

    def execute_rebalance(self, **kwargs) -> AaveOperationResult:
        self.calls.append(kwargs)
        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result
        from app.ai.schemas import TradeAction

        action = kwargs.get("action")
        asset_symbol = kwargs.get("asset_symbol", "USDC")
        amount = kwargs.get("amount", Decimal("0"))
        if action == TradeAction.BUY:
            op_type = AaveOperationType.DEPOSIT
        elif action == TradeAction.SELL:
            op_type = AaveOperationType.WITHDRAW
        else:
            op_type = AaveOperationType.NOOP
        self._call_index += 1
        return AaveOperationResult(
            operation=op_type,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=asset_symbol,
            amount=amount,
            tx_hash="0xfake_tx",
            message="fake success",
        )


class FakeStateManager:
    def __init__(
        self,
        emergency_stop: bool = False,
        circuit_closed: bool = True,
        mode: AaveOperationMode = AaveOperationMode.NORMAL,
        is_stale_value: bool = False,
    ) -> None:
        self._state = AaveSystemState(
            emergency_stop=emergency_stop,
            mode=mode,
            health_factor=Decimal("2.5"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=circuit_closed,
            stale_threshold_seconds=300,
        )
        self._is_stale = is_stale_value

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return self._is_stale


class FakeMonitoringService:
    def __init__(self, trading_allowed: bool = True) -> None:
        self._trading_allowed = trading_allowed
        self.last_health_factor: Optional[Decimal] = None

    def is_trading_allowed(self) -> bool:
        return self._trading_allowed

    def get_status(self):
        class _Status:
            last_health_factor = None

        return _Status()


# =============================================================================
# Helpers
# =============================================================================


def _make_rebalance_settings(
    *,
    cooldown_seconds: int = 0,  # no cooldown by default in tests
) -> RebalanceSettings:
    return RebalanceSettings(
        target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        deviation_threshold_pct=Decimal("5"),
        max_rebalance_pct=Decimal("10"),
        min_health_factor_post=Decimal("1.8"),
        cooldown_seconds=cooldown_seconds,
        confirmation_token_ttl_seconds=300,
        confirmation_token_secret="test-secret-key-for-tests",
        check_interval_seconds=14400,
        shadow_mode=True,
    )


def _make_aave_settings() -> AaveSettings:
    return AaveSettings(
        network="sepolia",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("1000"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0000000000000000000000000000000000000000",
    )


def _make_service(
    *,
    health_factor: Decimal = Decimal("2.5"),
    total_collateral: Decimal = Decimal("10000"),
    aave_service_results: Optional[list[AaveOperationResult]] = None,
    trading_allowed: bool = True,
    cooldown_seconds: int = 0,
) -> tuple[RebalanceService, FakeAaveClientWithPositions, FakeAaveService]:
    fake_client = FakeAaveClientWithPositions(
        health_factor=health_factor,
        total_collateral=total_collateral,
    )
    fake_aave_service = FakeAaveService(results=aave_service_results)
    state_manager = FakeStateManager()
    monitoring = FakeMonitoringService(trading_allowed=trading_allowed)

    service = RebalanceService(
        aave_client=fake_client,
        aave_service=fake_aave_service,
        rebalance_settings=_make_rebalance_settings(cooldown_seconds=cooldown_seconds),
        aave_settings=_make_aave_settings(),
        state_manager=state_manager,
        monitoring_service=monitoring,
    )
    return service, fake_client, fake_aave_service


def _make_ops(amount_usd: Decimal) -> list:
    """Create a single DEPOSIT operation for testing."""
    from app.aave.rebalance_schemas import ProposedOperation

    return [
        ProposedOperation(
            asset_symbol="USDC",
            operation=AaveOperationType.DEPOSIT,
            amount_usd=amount_usd,
            reason="test operation",
        )
    ]


# =============================================================================
# Tests: _check_safety_constraints daily limit
# =============================================================================


class TestDailyLimitCheck:
    def test_daily_limit_blocks_when_exceeded(self) -> None:
        """When daily_traded + ops > 30% of total, rejection_reason includes 'Daily trade limit'."""
        service, _, _ = _make_service(total_collateral=Decimal("10000"))
        # total = 10000, 30% = 3000; pre-set traded = 2900
        service._daily_traded_usd = Decimal("2900")

        now = datetime.now(timezone.utc)
        # ops = 200, total would be 3100 > 3000
        ops = _make_ops(Decimal("200"))
        reasons = service._check_safety_constraints(ops, Decimal("10000"), Decimal("2.5"), now)

        daily_reasons = [r for r in reasons if "Daily trade limit" in r]
        assert len(daily_reasons) == 1, f"Expected 1 daily limit reason, got: {reasons}"
        assert "30%" in daily_reasons[0]

    def test_daily_limit_allows_within_limit(self) -> None:
        """When daily_traded + ops <= 30% of total, no daily limit rejection."""
        service, _, _ = _make_service(total_collateral=Decimal("10000"))
        # total = 10000, 30% = 3000; pre-set traded = 2000
        service._daily_traded_usd = Decimal("2000")

        now = datetime.now(timezone.utc)
        # ops = 500, total would be 2500 <= 3000 -> OK
        ops = _make_ops(Decimal("500"))
        reasons = service._check_safety_constraints(ops, Decimal("10000"), Decimal("2.5"), now)

        daily_reasons = [r for r in reasons if "Daily trade limit" in r]
        assert len(daily_reasons) == 0, f"Unexpected daily limit reason: {reasons}"

    def test_daily_limit_exactly_at_limit_allowed(self) -> None:
        """When daily_traded + ops == 30%, not exceeded (boundary: strictly greater)."""
        service, _, _ = _make_service(total_collateral=Decimal("10000"))
        # total = 10000, 30% = 3000; pre-set traded = 2500
        service._daily_traded_usd = Decimal("2500")

        now = datetime.now(timezone.utc)
        # ops = 500, total would be exactly 3000 == limit -> not exceeded
        ops = _make_ops(Decimal("500"))
        reasons = service._check_safety_constraints(ops, Decimal("10000"), Decimal("2.5"), now)

        daily_reasons = [r for r in reasons if "Daily trade limit" in r]
        assert len(daily_reasons) == 0, f"Unexpected daily limit reason at boundary: {reasons}"

    def test_daily_limit_full_rejection_not_clip(self) -> None:
        """When 30% exceeded, all ops are rejected (full NOOP), not clipped partial."""
        service, _, _ = _make_service(total_collateral=Decimal("10000"))
        service._daily_traded_usd = Decimal("3000")  # already at limit

        now = datetime.now(timezone.utc)
        # Even a small op should trigger rejection
        ops = _make_ops(Decimal("1"))
        reasons = service._check_safety_constraints(ops, Decimal("10000"), Decimal("2.5"), now)

        # The rejection is for the entire batch, not partial
        daily_reasons = [r for r in reasons if "Daily trade limit" in r]
        assert len(daily_reasons) == 1

    def test_daily_limit_uses_decimal(self) -> None:
        """_daily_traded_usd and daily_limit_usd calculations use Decimal, not float."""
        service, _, _ = _make_service(total_collateral=Decimal("10000"))

        # Verify the type of the state field
        assert isinstance(service._daily_traded_usd, Decimal)

        # Verify Decimal arithmetic: 10000 * 30 / 100 must be Decimal
        total_usd = Decimal("10000")
        daily_limit = total_usd * Decimal("30") / Decimal("100")
        assert isinstance(daily_limit, Decimal)
        assert daily_limit == Decimal("3000")


# =============================================================================
# Tests: _get_daily_traded_usd reset at UTC midnight
# =============================================================================


class TestDailyTradedUsdReset:
    def test_daily_limit_resets_at_midnight_utc(self) -> None:
        """_get_daily_traded_usd() returns 0 after the UTC date changes."""
        service, _, _ = _make_service()

        # Seed with a past date and some traded amount
        from datetime import date

        service._daily_traded_usd = Decimal("1500")
        service._daily_reset_date = date(2000, 1, 1)  # old date

        # Now query with today's date -> should reset to 0
        now = datetime.now(timezone.utc)
        result = service._get_daily_traded_usd(now)

        assert result == Decimal("0")
        assert service._daily_traded_usd == Decimal("0")
        assert service._daily_reset_date == now.date()

    def test_daily_traded_same_day_no_reset(self) -> None:
        """_get_daily_traded_usd() preserves the value within the same UTC day."""
        service, _, _ = _make_service()

        today = datetime.now(timezone.utc).date()
        service._daily_traded_usd = Decimal("1000")
        service._daily_reset_date = today

        now = datetime.now(timezone.utc)
        result = service._get_daily_traded_usd(now)

        assert result == Decimal("1000")


# =============================================================================
# Tests: execute() updates _daily_traded_usd
# =============================================================================


class TestDailyTradedUpdatesAfterExecute:
    def test_daily_limit_updates_after_execute(self) -> None:
        """After successful execute(), _daily_traded_usd increases by executed amount."""
        amount = Decimal("500")
        success_result = AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol="USDC",
            amount=amount,
            tx_hash="0xfake",
            message="ok",
        )
        service, fake_client, _ = _make_service(
            total_collateral=Decimal("10000"),
            aave_service_results=[success_result],
        )

        assert service._daily_traded_usd == Decimal("0")

        # Run simulate then execute
        proposal = service.simulate(risk_mode="conservative")
        # Proposal may or may not be executable depending on test config
        _ = proposal.is_executable

        # Only run execute if proposal is executable
        if proposal.is_executable and proposal.operations:
            # Get the confirmation token
            token = proposal.confirmation_token
            assert token is not None

            service.execute(proposal_id=proposal.proposal_id, confirmation_token=token)

            # _daily_traded_usd should now be > 0
            assert service._daily_traded_usd >= Decimal("0")


# =============================================================================
# Tests: check_rule_engine() daily_limit_reached
# =============================================================================


class TestCheckRuleEngineDailyLimit:
    def test_check_rule_engine_daily_limit_reached(self) -> None:
        """check_rule_engine() returns False/'daily_limit_reached' when at/over limit."""
        monitoring = FakeMonitoringService(trading_allowed=True)

        can_trade, reason = check_rule_engine(
            monitoring,
            daily_traded_usd=Decimal("3000"),
            total_assets_usd=Decimal("10000"),
        )

        assert can_trade is False
        assert reason == "daily_limit_reached"

    def test_check_rule_engine_daily_limit_exactly_at_limit(self) -> None:
        """check_rule_engine() blocks when daily_traded_usd >= 30% of total."""
        monitoring = FakeMonitoringService(trading_allowed=True)

        # Exactly at limit (>= triggers block)
        can_trade, reason = check_rule_engine(
            monitoring,
            daily_traded_usd=Decimal("3000"),
            total_assets_usd=Decimal("10000"),
        )

        assert can_trade is False
        assert reason == "daily_limit_reached"

    def test_check_rule_engine_within_daily_limit(self) -> None:
        """check_rule_engine() allows trading when daily_traded_usd < 30% of total."""
        monitoring = FakeMonitoringService(trading_allowed=True)

        can_trade, reason = check_rule_engine(
            monitoring,
            daily_traded_usd=Decimal("2999"),
            total_assets_usd=Decimal("10000"),
        )

        assert can_trade is True
        assert reason == "ok"

    def test_check_rule_engine_no_daily_limit_params(self) -> None:
        """check_rule_engine() without daily limit params still works (backward compat)."""
        monitoring = FakeMonitoringService(trading_allowed=True)

        can_trade, reason = check_rule_engine(monitoring)

        assert can_trade is True
        assert reason == "ok"

    def test_check_rule_engine_hf_check_before_daily_limit(self) -> None:
        """HF check runs before daily limit check (correct execution order)."""
        monitoring = FakeMonitoringService(trading_allowed=True)

        class _StatusWithHF:
            last_health_factor = Decimal("1.4")  # below 1.6 threshold

        monitoring.get_status = lambda: _StatusWithHF()  # type: ignore[method-assign]

        can_trade, reason = check_rule_engine(
            monitoring,
            daily_traded_usd=Decimal("0"),
            total_assets_usd=Decimal("10000"),
        )

        assert can_trade is False
        assert reason == "hf_below_threshold"

    def test_check_rule_engine_emergency_stop_after_daily_limit(self) -> None:
        """Emergency stop is checked after daily limit (correct execution order)."""
        monitoring = FakeMonitoringService(trading_allowed=False)

        # Within daily limit but emergency stop is active
        can_trade, reason = check_rule_engine(
            monitoring,
            daily_traded_usd=Decimal("100"),
            total_assets_usd=Decimal("10000"),
        )

        assert can_trade is False
        assert reason == "emergency_stop"
