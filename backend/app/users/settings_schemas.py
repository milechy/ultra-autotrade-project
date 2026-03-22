# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_schemas.py
"""ユーザー設定APIのスキーマ定義。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_active: bool
    notification_email: Optional[str]
    notification_frequency: str
    max_single_trade_usd: Optional[Decimal]
    max_daily_trade_usd: Optional[Decimal]


class UserSettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    notification_frequency: Optional[str] = None
    max_single_trade_usd: Optional[Decimal] = None
    max_daily_trade_usd: Optional[Decimal] = None
