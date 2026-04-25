# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/schemas.py
"""提案APIのスキーマ定義。"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ProposalCreate(BaseModel):
    user_id: int
    ai_decision_id: Optional[int] = None
    operation: str
    asset: str
    amount: Decimal
    amount_usd: Decimal
    reason: str
    expected_hf_after: Optional[Decimal] = None
    estimated_gas_usd: Optional[Decimal] = None
    fee_rate: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    expires_at: Optional[datetime] = None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    ai_decision_id: Optional[int]
    operation: str
    asset: str
    amount: Decimal
    amount_usd: Decimal
    reason: str
    expected_hf_after: Optional[Decimal]
    estimated_gas_usd: Optional[Decimal]
    fee_rate: Optional[Decimal]
    fee_amount: Optional[Decimal]
    status: str
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    executed_at: Optional[datetime]
    tx_hash: Optional[str]
    error_message: Optional[str] = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ProposalListResponse(BaseModel):
    items: List[ProposalResponse]
    total: int


class AdminProposalItem(ProposalResponse):
    """管理者向け提案レスポンス（ユーザー名付き）。"""

    username: Optional[str] = None
    email: Optional[str] = None


class AdminProposalListResponse(BaseModel):
    items: List[AdminProposalItem]
    total: int
    page: int
    limit: int


class AdminProposalStats(BaseModel):
    """KPIカード用の提案統計。DB集計値なのでページネーションに依存しない。"""

    pending: int
    today_approved: int
    today_rejected: int
    expired: int
