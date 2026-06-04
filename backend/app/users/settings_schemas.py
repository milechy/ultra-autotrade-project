# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_schemas.py
"""ユーザー設定APIのスキーマ定義。"""

from datetime import datetime
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
    user_mode: str
    execution_policy: str
    line_monthly_opt_in: bool = False
    # 重要事項確認同意日時（User.terms_accepted_at を公開）
    terms_agreed_at: Optional[datetime] = None


class UserSettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    notification_frequency: Optional[str] = None
    max_single_trade_usd: Optional[Decimal] = None
    max_daily_trade_usd: Optional[Decimal] = None
    user_mode: Optional[str] = None
    execution_policy: Optional[str] = None
    line_monthly_opt_in: Optional[bool] = None
