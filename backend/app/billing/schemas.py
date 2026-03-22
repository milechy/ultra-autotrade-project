# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/schemas.py
"""
Billing モジュールの Pydantic v2 スキーマ定義。
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class PeriodType(str, Enum):
    """手数料計算の期間種別。"""

    DAILY = "daily"
    MONTHLY = "monthly"


class FeeConfigResponse(BaseModel):
    """FeeConfig レスポンス。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    management_fee_rate: Decimal = Field(description="管理報酬率（年率）")
    performance_fee_rate: Decimal = Field(description="成果報酬率")
    high_water_mark_enabled: bool = Field(description="HWM 使用フラグ")
    minimum_aum: Decimal = Field(description="最低 AUM")
    created_at: datetime
    updated_at: datetime


class FeeCalculationResponse(BaseModel):
    """FeeCalculation レスポンス。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    calculation_date: date
    period_type: str
    aum_snapshot: Decimal
    management_fee: Decimal
    performance_fee: Decimal
    total_fee: Decimal
    profit_since_hwm: Decimal
    high_water_mark: Decimal
    created_at: datetime


class FeeSummaryResponse(BaseModel):
    """ユーザーの手数料累計サマリー。"""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    total_management_fee: Decimal = Field(description="管理報酬の累計")
    total_performance_fee: Decimal = Field(description="成果報酬の累計")
    total_fee: Decimal = Field(description="合計手数料の累計")
    calculation_count: int = Field(description="計算レコード数")


class BatchResult(BaseModel):
    """バッチ実行結果。"""

    model_config = ConfigDict(from_attributes=True)

    processed_count: int = Field(description="正常処理ユーザー数")
    failed_count: int = Field(description="エラーユーザー数")
    errors: List[str] = Field(default_factory=list, description="エラーメッセージ一覧")
