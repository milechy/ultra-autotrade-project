# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_rebalance_risk_mode.py

"""
Tests for risk_mode DB lookup and RiskProfileManager gating in RebalanceService.

Verifies that:
- risk_mode is fetched from DB per user_id
- is_action_allowed() gates operations by asset + confidence
- min_health_factor from RiskProfile blocks under-collateralized rebalances
- Fallback to 'conservative' on DB errors, None user_id, or invalid mode values
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock

from app.aave.client import AccountData
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

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAaveClientRisk:
    """AaveClient stub with configurable health_factor and total_collateral_usd."""

    def __init__(
        self,
        health_factor: Decimal = Decimal("2.5"),
        total_usd: Decimal = Decimal("10000"),
    ) -> None:
        self.health_factor = health_factor
        self.total_usd = total_usd

    def get_account_data(self, wallet: str) -> AccountData:
        return AccountData(
            total_collateral_usd=self.total_usd,
            total_debt_usd=Decimal("0"),
            available_borrows_usd=Decimal("0"),
            health_factor=self.health_factor,
        )


class FakeStateManagerRisk:
    """StateManager stub: normal state (no emergency, circuit closed)."""

    def __init__(self) -> None:
        self._state = AaveSystemState(
            emergency_stop=False,
            mode=AaveOperationMode.NORMAL,
            health_factor=Decimal("2.5"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=True,
            stale_threshold_seconds=300,
        )

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return False


class FakeMonitoringServiceRisk:
    """MonitoringService stub: trading always allowed."""

    def is_trading_allowed(self) -> bool:
        return True

    def update_health_factor(self, hf: Decimal) -> None:
        pass


class FakeAaveServiceRisk:
    """AaveService stub: all execute_rebalance calls succeed."""

    def execute_rebalance(
        self,
        action: object,
        amount: Decimal,
        asset_symbol: str,
        dry_run: bool = True,
    ) -> AaveOperationResult:
        return AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            asset_symbol=asset_symbol,
            amount=amount,
            status=AaveOperationStatus.SUCCESS,
            message="dry_run OK",
            tx_hash=None,
        )


class FakeUser:
    """Minimal User model stub."""

    def __init__(self, risk_mode: Optional[str]) -> None:
        self.id = "user-001"
        self.risk_mode = risk_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db_factory(risk_mode: Optional[str] = "conservative"):
    """Return a callable that returns a mock DB session yielding FakeUser."""
    mock_db = MagicMock()
    mock_user = FakeUser(risk_mode)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    return lambda: mock_db


def make_db_factory_no_user():
    """Return a DB session where user is not found."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    return lambda: mock_db


def make_db_factory_raise():
    """Return a DB session that raises on query."""

    def _raise():
        raise RuntimeError("DB connection failed")

    return _raise


def make_service(
    health_factor: Decimal = Decimal("2.5"),
    total_usd: Decimal = Decimal("1000"),
    db_factory=None,
    min_hf_post: Decimal = Decimal("1.0"),
    default_asset: str = "ETH",
    target_allocations: Optional[dict] = None,
) -> RebalanceService:
    """Build a RebalanceService with test-friendly settings.

    Uses total_usd=1000 and max_rebalance_pct=5 so that each operation
    is at most 50 USD (5% of 1000), which is below the 10% single-trade
    cap (100 USD). This ensures the 10% cap safety check does not block
    tests that verify risk profile / confidence gating.
    """
    if target_allocations is None:
        # Default: all balance in ETH, target is USDC → forces WITHDRAW ETH + DEPOSIT USDC ops
        target_allocations = {"USDC": Decimal("100")}

    rb_settings = RebalanceSettings(
        target_allocations=target_allocations,
        deviation_threshold_pct=Decimal("5"),
        max_rebalance_pct=Decimal("5"),
        min_health_factor_post=min_hf_post,
        cooldown_seconds=0,
        confirmation_token_ttl_seconds=300,
        confirmation_token_secret="test-secret",
        check_interval_seconds=3600,
        shadow_mode=True,
    )
    aave_settings = AaveSettings(
        network="test",
        default_asset_symbol=default_asset,
        max_single_trade_usd=Decimal("100000"),
        min_health_factor=Decimal("1.0"),
        warn_health_factor=Decimal("1.5"),
        trade_cooldown_seconds=0,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x" + "0" * 40,
    )
    return RebalanceService(
        aave_client=FakeAaveClientRisk(health_factor=health_factor, total_usd=total_usd),
        aave_service=FakeAaveServiceRisk(),
        rebalance_settings=rb_settings,
        aave_settings=aave_settings,
        state_manager=FakeStateManagerRisk(),
        monitoring_service=FakeMonitoringServiceRisk(),
        db_session_factory=db_factory,
    )


# ---------------------------------------------------------------------------
# Tests: conservative mode
# ---------------------------------------------------------------------------


class TestConservativeMode:
    def test_conservative_low_confidence_rejected(self):
        """conservative: confidence 0.65 < 0.70 threshold → skip."""
        # ETH is not in conservative allowed_assets, but let's also test confidence with USDC
        # Use USDC as current asset and DAI as target → WITHDRAW USDC + DEPOSIT DAI
        svc = make_service(
            db_factory=make_db_factory("conservative"),
            default_asset="USDC",
            target_allocations={"DAI": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.65"))
        assert not proposal.is_executable
        reasons_text = " ".join(proposal.rejection_reasons)
        assert (
            "conservative" in reasons_text.lower()
            or "0.65" in reasons_text
            or "Skipped" in reasons_text
        )

    def test_conservative_eth_asset_rejected(self):
        """conservative: ETH not in allowed_assets → skip."""
        svc = make_service(
            db_factory=make_db_factory("conservative"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        assert not proposal.is_executable
        assert any("ETH" in r or "conservative" in r for r in proposal.rejection_reasons)

    def test_conservative_usdc_high_confidence_allowed(self):
        """conservative: USDC + confidence 0.80 > 0.70 + HF=2.5 > 2.0 → executable."""
        # USDC → DAI: both stables, conservative allows both
        svc = make_service(
            health_factor=Decimal("2.5"),
            db_factory=make_db_factory("conservative"),
            default_asset="USDC",
            target_allocations={"DAI": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        assert proposal.is_executable, f"Expected executable, reasons: {proposal.rejection_reasons}"

    def test_conservative_hf_below_profile_minimum_rejected(self):
        """conservative: HF=1.9 < profile min_HF=2.0 → skip."""
        svc = make_service(
            health_factor=Decimal("1.9"),
            min_hf_post=Decimal("1.0"),  # rb_settings threshold low so only profile triggers
            db_factory=make_db_factory("conservative"),
            default_asset="USDC",
            target_allocations={"DAI": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        assert not proposal.is_executable
        assert any("2.0" in r or "conservative" in r for r in proposal.rejection_reasons)

    def test_conservative_profile_min_hf_is_2_0(self):
        """RiskProfile conservative.min_health_factor == Decimal('2.0')."""
        from app.aave.risk_profile import RiskProfileManager

        mgr = RiskProfileManager()
        profile = mgr.get_profile("conservative")
        assert profile.min_health_factor == Decimal("2.0")


# ---------------------------------------------------------------------------
# Tests: balanced mode
# ---------------------------------------------------------------------------


class TestBalancedMode:
    def test_balanced_low_confidence_rejected(self):
        """balanced: confidence 0.50 < 0.55 threshold → skip."""
        svc = make_service(
            db_factory=make_db_factory("balanced"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.50"))
        assert not proposal.is_executable
        assert any(
            "0.50" in r or "balanced" in r or "Skipped" in r for r in proposal.rejection_reasons
        )

    def test_balanced_eth_high_confidence_allowed(self):
        """balanced: ETH in allowed_assets, confidence 0.60 > 0.55 + HF=2.5 > 1.8 → executable."""
        svc = make_service(
            health_factor=Decimal("2.5"),
            db_factory=make_db_factory("balanced"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.60"))
        assert proposal.is_executable, f"Expected executable, reasons: {proposal.rejection_reasons}"

    def test_balanced_hf_below_profile_minimum_rejected(self):
        """balanced: HF=1.7 < profile min_HF=1.8 → skip."""
        svc = make_service(
            health_factor=Decimal("1.7"),
            min_hf_post=Decimal("1.0"),
            db_factory=make_db_factory("balanced"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.60"))
        assert not proposal.is_executable
        assert any("1.8" in r or "balanced" in r for r in proposal.rejection_reasons)


# ---------------------------------------------------------------------------
# Tests: aggressive mode
# ---------------------------------------------------------------------------


class TestAggressiveMode:
    def test_aggressive_low_confidence_rejected(self):
        """aggressive: confidence 0.35 < 0.40 threshold → skip."""
        svc = make_service(
            db_factory=make_db_factory("aggressive"),
            default_asset="MATIC",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.35"))
        assert not proposal.is_executable
        assert any(
            "0.35" in r or "aggressive" in r or "Skipped" in r for r in proposal.rejection_reasons
        )

    def test_aggressive_any_asset_allowed(self):
        """aggressive: MATIC + confidence 0.50 > 0.40 → executable."""
        svc = make_service(
            health_factor=Decimal("2.5"),
            db_factory=make_db_factory("aggressive"),
            default_asset="MATIC",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.50"))
        assert proposal.is_executable, f"Expected executable, reasons: {proposal.rejection_reasons}"

    def test_aggressive_hf_below_profile_minimum_rejected(self):
        """aggressive: HF=1.4 < profile min_HF=1.5 → skip."""
        svc = make_service(
            health_factor=Decimal("1.4"),
            min_hf_post=Decimal("1.0"),
            db_factory=make_db_factory("aggressive"),
            default_asset="MATIC",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.50"))
        assert not proposal.is_executable
        assert any("1.5" in r or "aggressive" in r for r in proposal.rejection_reasons)

    def test_aggressive_profile_min_hf_is_1_5(self):
        """RiskProfile aggressive.min_health_factor == Decimal('1.5')."""
        from app.aave.risk_profile import RiskProfileManager

        mgr = RiskProfileManager()
        profile = mgr.get_profile("aggressive")
        assert profile.min_health_factor == Decimal("1.5")


# ---------------------------------------------------------------------------
# Tests: fallback behavior
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    def test_no_user_id_uses_fallback_conservative(self):
        """user_id=None → uses provided risk_mode fallback (conservative)."""
        # ETH not in conservative → should reject
        svc = make_service(
            db_factory=make_db_factory("aggressive"),  # DB says aggressive but won't be queried
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        # No user_id → uses risk_mode param default "conservative"
        proposal = svc.simulate(risk_mode="conservative", user_id=None, confidence=Decimal("0.80"))
        assert not proposal.is_executable
        assert any("ETH" in r or "conservative" in r for r in proposal.rejection_reasons)

    def test_invalid_risk_mode_falls_back_to_conservative(self):
        """risk_mode='invalid_value' in DB → conservative fallback."""
        svc = make_service(
            db_factory=make_db_factory("invalid_mode"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        # ETH not in conservative → should reject (proves conservative was used)
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        assert not proposal.is_executable
        assert any("ETH" in r or "conservative" in r for r in proposal.rejection_reasons)

    def test_db_exception_falls_back_to_conservative(self, caplog):
        """DB connection failure → conservative fallback → ETH rejected."""
        svc = make_service(
            db_factory=make_db_factory_raise(),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        with caplog.at_level(logging.WARNING):
            proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        # ETH not in conservative → rejected
        assert not proposal.is_executable
        # Warning was logged about DB error
        assert any("DB error" in r or "conservative" in r for r in caplog.text.splitlines() + [""])

    def test_user_not_found_falls_back_to_conservative(self, caplog):
        """User not in DB → conservative fallback."""
        svc = make_service(
            db_factory=make_db_factory_no_user(),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        with caplog.at_level(logging.WARNING):
            proposal = svc.simulate(user_id="user-999", confidence=Decimal("0.80"))
        assert not proposal.is_executable
        assert any("conservative" in r or "ETH" in r for r in proposal.rejection_reasons)

    def test_risk_mode_none_in_db_uses_conservative(self):
        """risk_mode=None in DB (NULL) → conservative fallback."""
        svc = make_service(
            db_factory=make_db_factory(None),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.80"))
        assert not proposal.is_executable


# ---------------------------------------------------------------------------
# Tests: DB lookup and log output
# ---------------------------------------------------------------------------


class TestRiskModeDbLookup:
    def test_risk_mode_fetched_from_db(self):
        """DB returns aggressive → ETH allowed with confidence 0.50."""
        svc = make_service(
            health_factor=Decimal("2.5"),
            db_factory=make_db_factory("aggressive"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        proposal = svc.simulate(user_id="user-001", confidence=Decimal("0.50"))
        assert proposal.is_executable, f"Expected executable, reasons: {proposal.rejection_reasons}"

    def test_risk_mode_log_output(self, caplog):
        """Log contains 'User user-001 risk_mode=balanced, action=...'."""
        svc = make_service(
            health_factor=Decimal("2.5"),
            db_factory=make_db_factory("balanced"),
            default_asset="ETH",
            target_allocations={"USDC": Decimal("100")},
        )
        with caplog.at_level(logging.INFO):
            svc.simulate(user_id="user-001", confidence=Decimal("0.60"))
        assert any("user-001" in line and "balanced" in line for line in caplog.text.splitlines())

    def test_no_db_factory_uses_fallback_risk_mode(self):
        """No db_session_factory → uses risk_mode param directly."""
        svc = make_service(
            db_factory=None,  # No DB
            default_asset="USDC",
            target_allocations={"DAI": Decimal("100")},
        )
        # balanced: USDC allowed, confidence=0.60 > 0.55 → should be executable
        proposal = svc.simulate(risk_mode="balanced", user_id=None, confidence=Decimal("0.60"))
        assert proposal.is_executable, f"Expected executable, reasons: {proposal.rejection_reasons}"

    def test_resolve_risk_mode_direct_conservative(self):
        """_resolve_risk_mode with user_id=None returns provided fallback."""
        svc = make_service(db_factory=None)
        assert svc._resolve_risk_mode(None, fallback="balanced") == "balanced"

    def test_resolve_risk_mode_invalid_fallback(self):
        """_resolve_risk_mode with invalid fallback returns 'conservative'."""
        svc = make_service(db_factory=None)
        assert svc._resolve_risk_mode(None, fallback="ultra_risky") == "conservative"
