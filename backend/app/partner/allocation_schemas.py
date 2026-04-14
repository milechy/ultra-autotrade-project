# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/allocation_schemas.py
"""資金割り振り API スキーマ定義。全金額フィールドは Decimal 型。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AllocationCreateRequest(BaseModel):
    """資金割り振り作成リクエスト。"""

    tester_name: str
    tester_user_id: Optional[int] = None  # Phase 1.5: FK to users.id（省略時はNone）
    allocated_amount_usd: Decimal
    notes: Optional[str] = None

    @field_validator("allocated_amount_usd")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("allocated_amount_usd must be positive")
        return v

    @field_validator("tester_name")
    @classmethod
    def tester_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tester_name must not be empty")
        return v.strip()


class AllocationUpdateRequest(BaseModel):
    """資金割り振り更新リクエスト（全フィールド任意）。"""

    tester_name: Optional[str] = None
    allocated_amount_usd: Optional[Decimal] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("allocated_amount_usd")
    @classmethod
    def amount_must_be_positive_if_set(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= Decimal("0"):
            raise ValueError("allocated_amount_usd must be positive")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "withdrawn"):
            raise ValueError("status must be 'active' or 'withdrawn'")
        return v


class AllocationResponse(BaseModel):
    """資金割り振りレスポンス。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: int
    tester_name: str
    tester_user_id: Optional[int] = None  # Phase 1.5: FK to users.id
    allocated_amount_usd: Decimal
    status: str
    allocated_at: datetime
    withdrawn_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class TesterPerformance(BaseModel):
    """テスター別パフォーマンス。"""

    allocation_id: int
    tester_name: str
    allocated_amount_usd: Decimal
    current_value_usd: Decimal
    pnl_usd: Decimal
    pnl_percentage: Decimal  # 既に % 変換済み（フロントで再変換しない）
    allocation_ratio: Decimal  # 0.0 〜 1.0


class PerformanceSummary(BaseModel):
    """パートナー全体のパフォーマンスサマリー。"""

    total_allocated_usd: Decimal
    total_supply_usd: Decimal  # Aave get_account_data().total_collateral_usd
    health_factor: Decimal  # Infinity → Decimal("999.0")
    testers: list[TesterPerformance]


class MyAllocationResponse(BaseModel):
    """テスター自身の割り振り情報レスポンス。"""

    allocated_amount_usd: Decimal
    current_value_usd: Optional[Decimal] = None
    partner_name: str
    status: str
    allocated_at: datetime
    pnl_usd: Optional[Decimal] = None
    pnl_percentage: Optional[Decimal] = None
    is_live: bool = False
