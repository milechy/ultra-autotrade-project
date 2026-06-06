# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_schemas.py
"""ユーザー設定APIのスキーマ定義。"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # 同意時の規約バージョン（フロントエンドの再同意判定に使用）
    terms_version: Optional[str] = None


class UserSettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    notification_frequency: Optional[str] = None
    max_single_trade_usd: Optional[Decimal] = None
    max_daily_trade_usd: Optional[Decimal] = None
    user_mode: Optional[str] = None
    execution_policy: Optional[str] = None
    line_monthly_opt_in: Optional[bool] = None
    # ユーザー名（本人による表示名変更）。auth/schemas.py の登録時 validator と同一規則。
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()
