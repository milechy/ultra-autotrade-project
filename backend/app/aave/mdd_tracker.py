# backend/app/aave/mdd_tracker.py

"""Max Drawdown Tracker for Aave portfolio risk management."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

MDD_THRESHOLDS = {
    "conservative": {"warning": Decimal("-0.05"), "hard_stop": Decimal("-0.10")},
    "balanced": {"warning": Decimal("-0.10"), "hard_stop": Decimal("-0.20")},
    "aggressive": {"warning": Decimal("-0.15"), "hard_stop": Decimal("-0.30")},
}


@dataclass
class MddStatus:
    current_value: Decimal
    peak_value: Decimal
    drawdown_pct: Decimal
    warning: bool
    hard_stop: bool
    risk_mode: str


class MddTracker:
    def __init__(self) -> None:
        self._peak: Optional[Decimal] = None
        self._current: Optional[Decimal] = None

    def update(self, current_value: Decimal) -> None:
        """Update tracker with current portfolio value."""
        if self._peak is None or current_value > self._peak:
            self._peak = current_value
        self._current = current_value

    def check_limits(self, risk_mode: str) -> MddStatus:
        """Check if drawdown exceeds thresholds for given risk mode."""
        if risk_mode not in MDD_THRESHOLDS:
            raise ValueError(f"Unknown risk_mode: {risk_mode}")
        if self._peak is None or self._peak == Decimal("0"):
            return MddStatus(
                current_value=Decimal("0"),
                peak_value=Decimal("0"),
                drawdown_pct=Decimal("0"),
                warning=False,
                hard_stop=False,
                risk_mode=risk_mode,
            )
        current = self._current if self._current is not None else Decimal("0")
        drawdown = (current - self._peak) / self._peak
        thresholds = MDD_THRESHOLDS[risk_mode]
        return MddStatus(
            current_value=current,
            peak_value=self._peak,
            drawdown_pct=drawdown,
            warning=drawdown <= thresholds["warning"],
            hard_stop=drawdown <= thresholds["hard_stop"],
            risk_mode=risk_mode,
        )

    def get_status(self) -> dict[str, Any]:
        """Return current tracker state as dict."""
        return {
            "peak": str(self._peak) if self._peak is not None else None,
            "current": str(self._current) if self._current is not None else None,
        }
