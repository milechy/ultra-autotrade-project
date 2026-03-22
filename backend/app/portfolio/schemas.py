# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/schemas.py
"""ポートフォリオ履歴APIのスキーマ定義。"""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class PortfolioSnapshotCreate(BaseModel):
    user_id: int
    total_value_usd: Decimal
    total_supply_usd: Decimal
    total_borrow_usd: Decimal
    health_factor: Optional[Decimal] = None
    positions_json: Optional[List[Any]] = None
    recorded_at: Optional[datetime] = None


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
