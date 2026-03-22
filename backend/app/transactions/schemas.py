# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/transactions/schemas.py
"""取引履歴APIのスキーマ定義。"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    user_id: int
    wallet_address: Optional[str] = None
    operation: str
    asset: str
    amount: Decimal
    amount_usd: Decimal
    tx_hash: Optional[str] = None
    chain: str
    status: str = "pending"
    ai_decision_id: Optional[int] = None
    gas_used: Optional[Decimal] = None
    gas_price_gwei: Optional[Decimal] = None
    is_dry_run: bool = False


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    wallet_address: Optional[str]
    operation: str
    asset: str
    amount: Decimal
    amount_usd: Decimal
    tx_hash: Optional[str]
    chain: str
    status: str
    ai_decision_id: Optional[int]
    gas_used: Optional[Decimal]
    gas_price_gwei: Optional[Decimal]
    is_dry_run: bool
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    limit: int
    offset: int


class TransactionStatsResponse(BaseModel):
    total_count: int
    success_count: int
    total_amount_usd: Decimal
    total_gas_usd: Decimal
