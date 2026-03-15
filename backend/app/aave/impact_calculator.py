from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class ImpactParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_balance_usd: Decimal
    current_apy: Decimal  # e.g. 0.05 = 5%
    proposed_apy: Decimal  # APY after action
    action_amount_usd: Decimal  # deposit amount (positive) or 0 for hold
    days: int = 30


class ImpactResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    gain_with_action_usd: Decimal
    gain_without_action_usd: Decimal
    net_difference_usd: Decimal

    @field_serializer("gain_with_action_usd", "gain_without_action_usd", "net_difference_usd")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class FormattedImpact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    net_difference_usd: Decimal
    net_difference_jpy: Decimal
    metaphor: str

    @field_serializer("net_difference_usd", "net_difference_jpy")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class ImpactCalculator:
    DEFAULT_EXCHANGE_RATE = Decimal("150")  # USD → JPY

    def calculate_impact(self, params: ImpactParams) -> ImpactResult:
        days_ratio = Decimal(str(params.days)) / Decimal("365")

        new_balance = params.current_balance_usd + params.action_amount_usd
        gain_with = (new_balance * params.proposed_apy * days_ratio).quantize(Decimal("0.000001"))
        gain_without = (params.current_balance_usd * params.current_apy * days_ratio).quantize(
            Decimal("0.000001")
        )
        net_diff = (gain_with - gain_without).quantize(Decimal("0.000001"))

        return ImpactResult(
            gain_with_action_usd=gain_with,
            gain_without_action_usd=gain_without,
            net_difference_usd=net_diff,
        )

    def format_comparison(
        self,
        result: ImpactResult,
        currency: str = "JPY",
        exchange_rate: Decimal | None = None,
    ) -> FormattedImpact:
        rate = exchange_rate if exchange_rate is not None else self.DEFAULT_EXCHANGE_RATE
        net_jpy = (result.net_difference_usd * rate).quantize(Decimal("1"))
        metaphor = self._metaphor(net_jpy)

        return FormattedImpact(
            net_difference_usd=result.net_difference_usd,
            net_difference_jpy=net_jpy,
            metaphor=metaphor,
        )

    def _metaphor(self, jpy: Decimal) -> str:
        abs_jpy = abs(jpy)
        if abs_jpy < Decimal("500"):
            return "自販機"
        elif abs_jpy < Decimal("1500"):
            return "コーヒー"
        elif abs_jpy < Decimal("5000"):
            return "ランチ"
        else:
            return "ディナー"
