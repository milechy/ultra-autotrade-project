# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class CurrentPosition(BaseModel):
    model_config = ConfigDict()

    asset_symbol: str
    amount: Decimal
    current_apy: Decimal
    net_rate: Decimal
    last_action_at: datetime

    @field_serializer("amount", "current_apy", "net_rate")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("last_action_at")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()


class ProposedAction(BaseModel):
    model_config = ConfigDict()

    asset_symbol: str
    amount: Decimal
    net_rate: Decimal
    action_type: str

    @field_serializer("amount", "net_rate")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class RuleCheckResult(BaseModel):
    model_config = ConfigDict()

    allowed: bool
    reason: str
    checks_passed: list[str]
    checks_failed: list[str]


class OptimizationRules:
    MIN_IMPROVEMENT_RATE: Decimal = Decimal("0.01")
    MIN_HOLDING_HOURS: int = 24
    MAX_SINGLE_MOVE_RATIO: Decimal = Decimal("0.30")
    HYSTERESIS_THRESHOLD: Decimal = Decimal("0.005")

    def should_rebalance(
        self,
        current: CurrentPosition,
        proposed: ProposedAction,
        total_assets: Decimal,
    ) -> RuleCheckResult:
        checks_passed: list[str] = []
        checks_failed: list[str] = []

        # Check 5: zero assets guard
        if total_assets <= Decimal("0"):
            checks_failed.append("zero_assets")
            return RuleCheckResult(
                allowed=False,
                reason="Total assets is zero or negative",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )
        checks_passed.append("zero_assets")

        # Check 1: minimum improvement
        improvement = proposed.net_rate - current.net_rate
        if improvement >= self.MIN_IMPROVEMENT_RATE:
            checks_passed.append("min_improvement")
        else:
            checks_failed.append("min_improvement")

        # Check 2: minimum holding period
        now = datetime.now(tz=timezone.utc)
        last = current.last_action_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_held = (now - last).total_seconds() / 3600
        if hours_held >= self.MIN_HOLDING_HOURS:
            checks_passed.append("min_holding")
        else:
            checks_failed.append("min_holding")

        # Check 3: partial move limit
        if proposed.amount <= total_assets * self.MAX_SINGLE_MOVE_RATIO:
            checks_passed.append("partial_move")
        else:
            checks_failed.append("partial_move")

        # Check 4: hysteresis
        rate_diff = abs(proposed.net_rate - current.net_rate)
        if rate_diff > self.HYSTERESIS_THRESHOLD:
            checks_passed.append("hysteresis")
        else:
            checks_failed.append("hysteresis")

        allowed = len(checks_failed) == 0
        if allowed:
            reason = "All checks passed"
        else:
            reason = f"Failed checks: {', '.join(checks_failed)}"

        return RuleCheckResult(
            allowed=allowed,
            reason=reason,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )
