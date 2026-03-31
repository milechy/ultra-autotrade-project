# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

_STABLE_SYMBOLS = {"USDC", "USDT", "DAI"}


class NetBenefitParams(BaseModel):
    model_config = ConfigDict()

    asset_symbol: str
    amount: Decimal
    supply_apy: Decimal
    incentive_apy: Decimal
    gas_cost_usd: Decimal
    holding_period_days: int
    volatility_30d: Decimal
    depeg_distance: Decimal

    @field_serializer(
        "amount", "supply_apy", "incentive_apy", "gas_cost_usd", "volatility_30d", "depeg_distance"
    )
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class NetBenefitResult(BaseModel):
    model_config = ConfigDict()

    asset_symbol: str
    expected_revenue: Decimal
    execution_cost: Decimal
    risk_penalty: Decimal
    net_benefit: Decimal
    annualized_net_rate: Decimal

    @field_serializer(
        "expected_revenue", "execution_cost", "risk_penalty", "net_benefit", "annualized_net_rate"
    )
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class NetBenefitCalculator:
    _QUANTIZE = Decimal("0.000001")

    def calculate(self, params: NetBenefitParams) -> NetBenefitResult:
        days = Decimal(str(params.holding_period_days))
        expected_revenue = (
            params.amount * (params.supply_apy + params.incentive_apy) * days / Decimal("365")
        )
        execution_cost = params.gas_cost_usd * Decimal("2")

        is_stable = params.asset_symbol.upper() in _STABLE_SYMBOLS
        if is_stable:
            volatility_penalty = params.amount * Decimal("0.001")
            depeg_penalty = params.amount * params.depeg_distance * Decimal("0.5")
            risk_penalty = volatility_penalty + depeg_penalty
        else:
            risk_penalty = params.amount * params.volatility_30d * Decimal("0.1")

        net_benefit = expected_revenue - execution_cost - risk_penalty

        if params.amount == Decimal("0") or params.holding_period_days == 0:
            annualized_net_rate = Decimal("0")
        else:
            annualized_net_rate = net_benefit / params.amount / days * Decimal("365")

        return NetBenefitResult(
            asset_symbol=params.asset_symbol,
            expected_revenue=expected_revenue.quantize(self._QUANTIZE),
            execution_cost=execution_cost.quantize(self._QUANTIZE),
            risk_penalty=risk_penalty.quantize(self._QUANTIZE),
            net_benefit=net_benefit.quantize(self._QUANTIZE),
            annualized_net_rate=annualized_net_rate.quantize(self._QUANTIZE),
        )

    def compare_assets(self, assets: list[NetBenefitParams]) -> list[NetBenefitResult]:
        results = [self.calculate(p) for p in assets]
        return sorted(results, key=lambda r: r.net_benefit, reverse=True)
