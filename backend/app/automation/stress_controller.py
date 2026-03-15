from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from app.aave.schemas import AaveOperationMode


@dataclass
class StressStage:
    trigger_pct: Optional[float]  # None = no price trigger (e.g. stage 4)
    action: str
    mode: AaveOperationMode


class MarketStressData(BaseModel):
    price_change_24h: float  # negative = drop, e.g. -0.12 for -12%
    health_factor: float
    manual_stop: bool
    current_mode: AaveOperationMode
    current_stage: int = 0


class StressEvaluation(BaseModel):
    stage: int
    action: str
    mode: AaveOperationMode
    reason: str


class WithdrawStep(BaseModel):
    asset_symbol: str
    amount: float  # percentage of position (0.0–1.0)
    priority: int


class WithdrawPlan(BaseModel):
    stage: int
    steps: list[WithdrawStep]
    total_withdraw: float  # estimated total withdrawal ratio


class StressController:
    STAGES: dict[int, StressStage] = {
        1: StressStage(trigger_pct=-0.10, action="pause_deposit", mode=AaveOperationMode.SAFE_MODE),
        2: StressStage(
            trigger_pct=-0.15, action="partial_withdraw", mode=AaveOperationMode.SAFE_MODE
        ),
        3: StressStage(
            trigger_pct=-0.20, action="safe_asset_retreat", mode=AaveOperationMode.SAFE_MODE
        ),
        4: StressStage(trigger_pct=None, action="hard_stop", mode=AaveOperationMode.HARD_STOP),
    }

    def evaluate(self, data: MarketStressData) -> StressEvaluation:
        """Evaluate market stress and return the appropriate stage/action.

        Stage 4 triggers on manual_stop OR health_factor < 1.6.
        Price-based stages: check most severe first (3→2→1).
        No-relaxation: result stage = max(computed, current_stage).
        """
        # Stage 4: hard stop conditions
        if data.manual_stop or data.health_factor < 1.6:
            reason_parts = []
            if data.manual_stop:
                reason_parts.append("manual_stop=True")
            if data.health_factor < 1.6:
                reason_parts.append(f"health_factor={data.health_factor} < 1.6")
            stage4 = self.STAGES[4]
            return StressEvaluation(
                stage=4,
                action=stage4.action,
                mode=stage4.mode,
                reason=" AND ".join(reason_parts),
            )

        # Price-based stages: check most severe first
        computed_stage = 0
        computed_reason = "normal market conditions"
        for stage_num in [3, 2, 1]:
            stage_def = self.STAGES[stage_num]
            if stage_def.trigger_pct is not None and data.price_change_24h <= stage_def.trigger_pct:
                computed_stage = stage_num
                computed_reason = (
                    f"price_change_24h={data.price_change_24h:.2%} <= {stage_def.trigger_pct:.2%}"
                )
                break

        # No-relaxation: never allow downgrade
        final_stage = max(computed_stage, data.current_stage)

        if final_stage == 0:
            return StressEvaluation(
                stage=0,
                action="normal",
                mode=AaveOperationMode.NORMAL,
                reason=computed_reason,
            )

        stage_def = self.STAGES[final_stage]
        reason = computed_reason
        if final_stage > computed_stage and data.current_stage > 0:
            reason = f"no-relaxation: current_stage={data.current_stage} retained (computed={computed_stage})"

        return StressEvaluation(
            stage=final_stage,
            action=stage_def.action,
            mode=stage_def.mode,
            reason=reason,
        )

    def get_withdraw_plan(self, stage: int) -> WithdrawPlan:
        """Return withdrawal plan for a given stage.

        Stage 2: withdraw 25% USDC
        Stage 3: withdraw 100% (USDC 60% + USDT 40%)
        Stage 4: NOOP (hard stop — no withdrawal plan)
        Others: NOOP
        """
        if stage == 2:
            return WithdrawPlan(
                stage=stage,
                steps=[
                    WithdrawStep(asset_symbol="USDC", amount=0.25, priority=1),
                ],
                total_withdraw=0.25,
            )
        elif stage == 3:
            return WithdrawPlan(
                stage=stage,
                steps=[
                    WithdrawStep(asset_symbol="USDC", amount=0.60, priority=1),
                    WithdrawStep(asset_symbol="USDT", amount=0.40, priority=2),
                ],
                total_withdraw=1.0,
            )
        else:
            # Stage 1, 4, or 0: NOOP
            return WithdrawPlan(
                stage=stage,
                steps=[],
                total_withdraw=0.0,
            )
