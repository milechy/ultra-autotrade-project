# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .risk_limiter import get_effective_limits


@dataclass
class RiskProfile:
    mode: str
    max_utilization: Decimal
    min_health_factor: Decimal
    allowed_assets: list[str]
    min_confidence: Decimal


class ActionAllowedResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    allowed: bool
    reason: str


_BASE_PROFILES: dict[str, RiskProfile] = {
    "conservative": RiskProfile(
        mode="conservative",
        max_utilization=Decimal("0.75"),
        min_health_factor=Decimal("2.0"),
        allowed_assets=["USDC", "USDT", "DAI"],
        min_confidence=Decimal("0.70"),
    ),
    "balanced": RiskProfile(
        mode="balanced",
        max_utilization=Decimal("0.85"),
        min_health_factor=Decimal("1.8"),
        allowed_assets=["USDC", "USDT", "DAI", "ETH", "WBTC"],
        min_confidence=Decimal("0.55"),
    ),
    "aggressive": RiskProfile(
        mode="aggressive",
        max_utilization=Decimal("0.92"),
        min_health_factor=Decimal("1.5"),
        allowed_assets=["USDC", "USDT", "DAI", "ETH", "WBTC", "MATIC", "LINK"],
        min_confidence=Decimal("0.40"),
    ),
}


def _get_profiles() -> dict[str, RiskProfile]:
    """Return profiles, optionally relaxing min_health_factor when custom limiter is active.

    Strict mode: profiles use their base min_health_factor unchanged.
    Custom mode:  profiles allow HF down to limits.hf_min (relaxed floor for testing),
                  but never below HF_HARD_MIN (enforced inside get_effective_limits()).
    """
    limits = get_effective_limits()
    result: dict[str, RiskProfile] = {}
    for key, base in _BASE_PROFILES.items():
        if limits.is_custom:
            # Relax: take the lower of base profile floor and custom limiter floor
            effective_hf = min(base.min_health_factor, limits.hf_min)
        else:
            effective_hf = base.min_health_factor
        result[key] = RiskProfile(
            mode=base.mode,
            max_utilization=base.max_utilization,
            min_health_factor=effective_hf,
            allowed_assets=base.allowed_assets,
            min_confidence=base.min_confidence,
        )
    return result


class RiskProfileManager:
    def get_profile(self, mode: str) -> RiskProfile:
        profiles = _get_profiles()
        return profiles.get(mode, profiles["conservative"])

    def is_action_allowed(
        self, mode: str, asset_symbol: str, confidence: Decimal
    ) -> ActionAllowedResult:
        profile = self.get_profile(mode)

        if asset_symbol not in profile.allowed_assets:
            return ActionAllowedResult(
                allowed=False,
                reason=f"{asset_symbol} は {mode} プロファイルで許可されていません",
            )

        if confidence < profile.min_confidence:
            return ActionAllowedResult(
                allowed=False,
                reason=f"信頼度 {confidence} が最低要件 {profile.min_confidence} を下回っています",
            )

        return ActionAllowedResult(allowed=True, reason="OK")
