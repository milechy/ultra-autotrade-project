# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_mdd_tracker.py

"""Tests for MddTracker (Max Drawdown Tracker)."""

from decimal import Decimal

import pytest

from app.aave.mdd_tracker import MddTracker


class TestMddTrackerNoDrawdown:
    def test_no_drawdown(self) -> None:
        """Value stays at peak — no warning, no hard_stop."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("1000"))

        status = tracker.check_limits("balanced")

        assert status.drawdown_pct == Decimal("0")
        assert status.warning is False
        assert status.hard_stop is False
        assert status.peak_value == Decimal("1000")
        assert status.current_value == Decimal("1000")

    def test_value_rises_above_peak(self) -> None:
        """Peak is updated when value rises — drawdown resets to 0."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("1200"))

        status = tracker.check_limits("conservative")

        assert status.peak_value == Decimal("1200")
        assert status.drawdown_pct == Decimal("0")
        assert status.warning is False
        assert status.hard_stop is False


class TestConservativeThresholds:
    def test_conservative_warning(self) -> None:
        """Drawdown of -6% triggers warning (threshold: -5%) for conservative."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("940"))  # -6%

        status = tracker.check_limits("conservative")

        assert status.warning is True
        assert status.hard_stop is False
        assert status.risk_mode == "conservative"

    def test_conservative_hard_stop(self) -> None:
        """Drawdown of -11% triggers hard_stop (threshold: -10%) for conservative."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("890"))  # -11%

        status = tracker.check_limits("conservative")

        assert status.warning is True
        assert status.hard_stop is True
        assert status.risk_mode == "conservative"

    def test_conservative_below_warning(self) -> None:
        """Drawdown of -3% is below conservative warning threshold (-5%)."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("970"))  # -3%

        status = tracker.check_limits("conservative")

        assert status.warning is False
        assert status.hard_stop is False


class TestBalancedThresholds:
    def test_balanced_warning(self) -> None:
        """Drawdown of -12% triggers warning (threshold: -10%) for balanced."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("880"))  # -12%

        status = tracker.check_limits("balanced")

        assert status.warning is True
        assert status.hard_stop is False
        assert status.risk_mode == "balanced"

    def test_balanced_hard_stop(self) -> None:
        """Drawdown of -21% triggers hard_stop (threshold: -20%) for balanced."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("790"))  # -21%

        status = tracker.check_limits("balanced")

        assert status.warning is True
        assert status.hard_stop is True

    def test_balanced_below_warning(self) -> None:
        """Drawdown of -8% is below balanced warning threshold (-10%)."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("920"))  # -8%

        status = tracker.check_limits("balanced")

        assert status.warning is False
        assert status.hard_stop is False


class TestAggressiveThresholds:
    def test_aggressive_warning(self) -> None:
        """Drawdown of -16% triggers warning (threshold: -15%) for aggressive."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("840"))  # -16%

        status = tracker.check_limits("aggressive")

        assert status.warning is True
        assert status.hard_stop is False
        assert status.risk_mode == "aggressive"

    def test_aggressive_hard_stop(self) -> None:
        """Drawdown of -31% triggers hard_stop (threshold: -30%) for aggressive."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("690"))  # -31%

        status = tracker.check_limits("aggressive")

        assert status.warning is True
        assert status.hard_stop is True

    def test_aggressive_below_warning(self) -> None:
        """Drawdown of -10% is below aggressive warning threshold (-15%)."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))
        tracker.update(Decimal("900"))  # -10%

        status = tracker.check_limits("aggressive")

        assert status.warning is False
        assert status.hard_stop is False


class TestUnknownRiskMode:
    def test_unknown_risk_mode_raises_value_error(self) -> None:
        """Unknown risk_mode raises ValueError."""
        tracker = MddTracker()
        tracker.update(Decimal("1000"))

        with pytest.raises(ValueError, match="Unknown risk_mode: invalid_mode"):
            tracker.check_limits("invalid_mode")


class TestNoUpdateState:
    def test_check_limits_before_update_returns_zero(self) -> None:
        """check_limits before any update returns zero drawdown, no flags."""
        tracker = MddTracker()

        status = tracker.check_limits("balanced")

        assert status.current_value == Decimal("0")
        assert status.peak_value == Decimal("0")
        assert status.drawdown_pct == Decimal("0")
        assert status.warning is False
        assert status.hard_stop is False

    def test_get_status_before_update(self) -> None:
        """get_status before any update returns None for both fields."""
        tracker = MddTracker()
        result = tracker.get_status()

        assert result["peak"] is None
        assert result["current"] is None

    def test_get_status_after_update(self) -> None:
        """get_status after update returns string representations."""
        tracker = MddTracker()
        tracker.update(Decimal("500"))
        tracker.update(Decimal("450"))

        result = tracker.get_status()

        assert result["peak"] == "500"
        assert result["current"] == "450"
