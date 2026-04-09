# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/schemas.py
"""パートナー統計 API スキーマ定義。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


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


class NotificationLogItem(BaseModel):
    """通知ログ1件分のレスポンス。"""

    id: int
    channel: str
    severity: str
    title: str
    body: str
    partner_id: Optional[int]
    user_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class TesterItem(BaseModel):
    """パートナーが招待したテスターの一覧アイテム。"""

    id: int
    username: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class NotificationLogPage(BaseModel):
    """通知ログ一覧ページネーションレスポンス。"""

    items: list[NotificationLogItem]
    total: int
    page: int
    per_page: int
