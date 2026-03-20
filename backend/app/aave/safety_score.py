# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class SafetyScoreParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    utilization_rate: Decimal  # 0.0-1.0
    health_factor: Decimal  # current HF (0 means no position)
    volatility_30d: Decimal  # 30-day volatility (0.0-1.0)


class SafetyBreakdown(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    util_score: Decimal  # 0-100
    hf_score: Decimal  # 0-100
    vol_score: Decimal  # 0-100

    @field_serializer("util_score", "hf_score", "vol_score")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class SafetyScoreResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    score: Decimal  # 0-100
    label: str  # Japanese label
    color: str  # green/blue/yellow/orange/red
    breakdown: SafetyBreakdown

    @field_serializer("score")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class SafetyScoreCalculator:
    WEIGHT_UTIL = Decimal("0.3")
    WEIGHT_HF = Decimal("0.4")
    WEIGHT_VOL = Decimal("0.3")

    def calculate(self, params: SafetyScoreParams) -> SafetyScoreResult:
        util_score = self._util_score(params.utilization_rate)
        hf_score = self._hf_score(params.health_factor)
        vol_score = self._vol_score(params.volatility_30d)

        score = (
            util_score * self.WEIGHT_UTIL + hf_score * self.WEIGHT_HF + vol_score * self.WEIGHT_VOL
        ).quantize(Decimal("0.01"))

        label, color = self._label_color(score)

        return SafetyScoreResult(
            score=score,
            label=label,
            color=color,
            breakdown=SafetyBreakdown(
                util_score=util_score,
                hf_score=hf_score,
                vol_score=vol_score,
            ),
        )

    def _util_score(self, utilization_rate: Decimal) -> Decimal:
        # Lower utilization = safer. 100% util = 0 score, 0% util = 100 score
        score = (Decimal("1") - utilization_rate) * Decimal("100")
        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    def _hf_score(self, health_factor: Decimal) -> Decimal:
        # No position → neutral 50
        if health_factor == Decimal("0"):
            return Decimal("50.00")
        # HF >= 3.0 → 100, HF <= 1.0 → 0
        score = ((health_factor - Decimal("1")) / Decimal("2")) * Decimal("100")
        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    def _vol_score(self, volatility_30d: Decimal) -> Decimal:
        # Lower volatility = safer. 0% vol = 100 score, 100% vol = 0 score
        score = (Decimal("1") - volatility_30d) * Decimal("100")
        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    def _label_color(self, score: Decimal) -> tuple[str, str]:
        if score >= Decimal("90"):
            return "とても安全", "green"
        elif score >= Decimal("70"):
            return "安全", "blue"
        elif score >= Decimal("50"):
            return "注意", "yellow"
        elif score >= Decimal("30"):
            return "警戒", "orange"
        else:
            return "危険", "red"
