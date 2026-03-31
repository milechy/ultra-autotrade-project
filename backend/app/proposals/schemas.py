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
    status: str
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    executed_at: Optional[datetime]
    tx_hash: Optional[str]
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ProposalListResponse(BaseModel):
    items: List[ProposalResponse]
    total: int
