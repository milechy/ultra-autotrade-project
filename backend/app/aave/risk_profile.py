# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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


_PROFILES: dict[str, RiskProfile] = {
    "conservative": RiskProfile(
        mode="conservative",
        max_utilization=Decimal("0.6"),
        min_health_factor=Decimal("2.0"),
        allowed_assets=["USDC", "USDT", "DAI"],
        min_confidence=Decimal("0.8"),
    ),
    "balanced": RiskProfile(
        mode="balanced",
        max_utilization=Decimal("0.75"),
        min_health_factor=Decimal("1.7"),
        allowed_assets=["USDC", "USDT", "DAI", "ETH", "WBTC"],
        min_confidence=Decimal("0.65"),
    ),
    "aggressive": RiskProfile(
        mode="aggressive",
        max_utilization=Decimal("0.9"),
        min_health_factor=Decimal("1.5"),
        allowed_assets=["USDC", "USDT", "DAI", "ETH", "WBTC", "MATIC", "LINK"],
        min_confidence=Decimal("0.5"),
    ),
}


class RiskProfileManager:
    def get_profile(self, mode: str) -> RiskProfile:
        return _PROFILES.get(mode, _PROFILES["conservative"])

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
