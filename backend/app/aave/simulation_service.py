# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class SimulationParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_balance_usd: Decimal
    current_apy: Decimal  # current APY
    proposed_apy: Decimal  # APY if supply action taken
    additional_amount_usd: Decimal  # deposit amount for supply scenario
    gas_cost_usd: Decimal  # estimated gas cost for withdraw
    days: int = 30


class ScenarioResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str  # "supply" | "withdraw" | "hold"
    projected_gain_usd: Decimal
    net_usd: Decimal  # projected_gain - costs

    @field_serializer("projected_gain_usd", "net_usd")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class SimulationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scenarios: list[ScenarioResult]
    best_scenario: str
    disclaimer: str


class SimulationService:
    DISCLAIMER = "シミュレーション結果は過去のデータに基づく参考値であり、将来の収益を保証するものではありません。"

    def simulate(self, params: SimulationParams) -> SimulationResult:
        days_ratio = Decimal(str(params.days)) / Decimal("365")

        # supply scenario
        supply_balance = params.current_balance_usd + params.additional_amount_usd
        supply_gain = (supply_balance * params.proposed_apy * days_ratio).quantize(
            Decimal("0.000001")
        )
        supply_net = supply_gain  # no cost assumed for supply

        # withdraw scenario
        withdraw_gain = Decimal("0")
        withdraw_net = (withdraw_gain - params.gas_cost_usd).quantize(Decimal("0.000001"))

        # hold scenario
        hold_gain = (params.current_balance_usd * params.current_apy * days_ratio).quantize(
            Decimal("0.000001")
        )
        hold_net = hold_gain

        scenarios = [
            ScenarioResult(name="supply", projected_gain_usd=supply_gain, net_usd=supply_net),
            ScenarioResult(name="withdraw", projected_gain_usd=withdraw_gain, net_usd=withdraw_net),
            ScenarioResult(name="hold", projected_gain_usd=hold_gain, net_usd=hold_net),
        ]

        best = max(scenarios, key=lambda s: s.projected_gain_usd)

        return SimulationResult(
            scenarios=scenarios,
            best_scenario=best.name,
            disclaimer=self.DISCLAIMER,
        )
