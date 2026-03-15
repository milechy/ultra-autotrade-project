from datetime import datetime
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, field_serializer


class UtilizationData(BaseModel):
    model_config = ConfigDict()

    asset_symbol: str
    utilization_rate: Decimal
    supply_apy: Decimal
    borrow_apy: Decimal
    available_liquidity: Decimal
    tvl: Decimal
    timestamp: datetime

    @field_serializer("utilization_rate", "supply_apy", "borrow_apy", "available_liquidity", "tvl")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("timestamp")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()


class SupplyRecommendation(BaseModel):
    model_config = ConfigDict()

    action: Literal["SUPPLY", "WAIT", "CAUTION"]
    reason: str
    utilization_rate: Decimal
    expected_apy: Decimal

    @field_serializer("utilization_rate", "expected_apy")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class UtilizationMonitor:
    def __init__(self, base_url: str = "https://aave-api-v2.aave.com") -> None:
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url)

    async def fetch_utilization(self, asset_symbol: str) -> UtilizationData:
        response = await self._client.get(f"/data/liquidity/v2?poolId={asset_symbol}")
        response.raise_for_status()
        data = response.json()
        return UtilizationData(
            asset_symbol=asset_symbol,
            utilization_rate=Decimal(str(data["utilizationRate"])),
            supply_apy=Decimal(str(data["supplyAPY"])),
            borrow_apy=Decimal(str(data["borrowAPY"])),
            available_liquidity=Decimal(str(data["availableLiquidity"])),
            tvl=Decimal(str(data["tvl"])),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )

    def evaluate(self, data: UtilizationData) -> SupplyRecommendation:
        rate = data.utilization_rate
        if rate > Decimal("0.95"):
            return SupplyRecommendation(
                action="CAUTION",
                reason="Utilization above 95%: liquidity risk is high",
                utilization_rate=rate,
                expected_apy=data.supply_apy,
            )
        if rate >= Decimal("0.80"):
            return SupplyRecommendation(
                action="SUPPLY",
                reason="Utilization in sweet spot (80-95%): APY is attractive",
                utilization_rate=rate,
                expected_apy=data.supply_apy,
            )
        return SupplyRecommendation(
            action="WAIT",
            reason="Utilization below 80%: APY not optimal",
            utilization_rate=rate,
            expected_apy=data.supply_apy,
        )
