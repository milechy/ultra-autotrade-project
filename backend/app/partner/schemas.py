# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/schemas.py
"""パートナー統計 API スキーマ定義。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PartnerStatsResponse(BaseModel):
    """パートナー配下ユーザー全体の KPI。"""

    total_aum: Decimal
    yesterday_aum: Decimal
    month_return_pct: Optional[Decimal]
    yesterday_return_pct: Optional[Decimal]
    user_count: int


class UserStatsResponse(BaseModel):
    """特定ユーザーの運用実績。"""

    user_id: int
    today_amount: Decimal
    month_amount: Decimal
    yesterday_return_pct: Optional[Decimal]
    month_return_pct: Optional[Decimal]


class MonthlyStatsResponse(BaseModel):
    """月別運用実績集計。"""

    month: str  # "YYYY-MM"
    start_value: Decimal
    end_value: Decimal
    return_pct: Decimal
    user_count: int
