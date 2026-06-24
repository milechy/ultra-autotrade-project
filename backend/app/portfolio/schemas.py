# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/schemas.py
"""ポートフォリオ履歴APIのスキーマ定義。"""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _cap_hf_inf(v: Optional[Decimal]) -> Optional[Decimal]:
    """Aave V3 ではポジションがないと HF=∞ を返す。finite_number 制約を回避するため 999.0 に丸める。"""
    if v is not None and isinstance(v, Decimal) and not v.is_finite():
        return Decimal("999.0")
    return v


class PortfolioSnapshotCreate(BaseModel):
    user_id: int
    total_value_usd: Decimal
    total_supply_usd: Decimal
    total_borrow_usd: Decimal
    health_factor: Optional[Decimal] = None
    positions_json: Optional[List[Any]] = None
    recorded_at: Optional[datetime] = None

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    total_value_usd: Decimal
    total_supply_usd: Decimal
    total_borrow_usd: Decimal
    health_factor: Optional[Decimal]
    positions_json: Optional[List[Any]]
    recorded_at: datetime

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)


class PortfolioHistoryResponse(BaseModel):
    items: List[PortfolioSnapshotResponse]
    total: int
    period: str
    interval: str


class PortfolioCurrentResponse(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    total_value_usd: Decimal = Decimal("0")
    total_supply_usd: Decimal = Decimal("0")
    total_borrow_usd: Decimal = Decimal("0")
    health_factor: Optional[Decimal] = None
    positions_json: Optional[List[Any]] = None
    recorded_at: Optional[datetime] = None
    has_data: bool = False
    # positions_json の apy_pct を value_usd で加重平均した APY (%)。
    # ポジション無し / value 合計 0 のときは "0.00"。財務値は Decimal 型。
    weighted_avg_apy: Decimal = Decimal("0")

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)


class PortfolioLiveResponse(BaseModel):
    """GET /api/portfolio ライブAaveデータレスポンス。"""

    total_supply_usd: Decimal
    total_borrow_usd: Decimal
    health_factor: Optional[Decimal]
    net_worth_usd: Decimal
    positions: list[Any] = []
    chain: str
    fetched_at: str  # ISO 8601

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)
