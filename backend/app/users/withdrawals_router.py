# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/withdrawals_router.py
"""
出金イベント記録 API ルーター (P4)。

ノンカストディアル出金:
- 出金は常にユーザー本人の Privy 鍵による署名で実行される。
- backend はオンチェーン送金には一切関与しない。tx_hash 記録のみ。
- delegated signing (P3) は出金には適用されない。本人署名のみ。

エンドポイント:
- POST /api/users/withdrawals  - 出金 tx のログ記録 (本人署名後にフロントから呼ばれる)
- GET  /api/users/withdrawals  - 自分の出金履歴一覧

NOTE: ルーター登録は backend/app/main.py で行う必要があるが、main.py は
Tier-S 不触のため、本 PR では含めない。別 PR で登録すること:
  from app.users.withdrawals_router import router as user_withdrawals_router
  app.include_router(user_withdrawals_router)  # User withdrawals (P4)
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db
from app.transactions.models import Transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users/withdrawals", tags=["user-withdrawals"])


# ------------------------------------------------------------------ schemas


class WithdrawalCreate(BaseModel):
    """出金イベント記録リクエスト。"""

    tx_hash: str = Field(..., min_length=66, max_length=66, description="0x prefix 付き 32-byte hash")
    to_address: str = Field(..., min_length=42, max_length=42, description="0x prefix 付き宛先アドレス")
    amount_usdc: Decimal = Field(..., gt=0, description="USDC 数量 (正の値)")
    network: str = Field(default="base", description="ネットワーク名 (base のみ対応)")

    @field_validator("tx_hash")
    @classmethod
    def _validate_tx_hash(cls, v: str) -> str:
        if not v.startswith("0x"):
            raise ValueError("tx_hash must start with 0x")
        # 0x + 64 hex chars
        try:
            int(v[2:], 16)
        except ValueError as e:
            raise ValueError("tx_hash must be hex") from e
        return v.lower()

    @field_validator("to_address")
    @classmethod
    def _validate_to_address(cls, v: str) -> str:
        if not v.startswith("0x"):
            raise ValueError("to_address must start with 0x")
        try:
            int(v[2:], 16)
        except ValueError as e:
            raise ValueError("to_address must be hex") from e
        return v.lower()

    @field_validator("network")
    @classmethod
    def _validate_network(cls, v: str) -> str:
        if v not in ("base",):
            raise ValueError("network must be 'base'")
        return v


class WithdrawalResponse(BaseModel):
    """出金イベント記録レスポンス。"""

    id: int
    user_id: int
    tx_hash: str
    to_address: str
    amount_usdc: Decimal
    network: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WithdrawalListResponse(BaseModel):
    """出金履歴一覧レスポンス。"""

    items: List[WithdrawalResponse]
    total: int


# ------------------------------------------------------------------ endpoints


@router.post(
    "",
    response_model=WithdrawalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="出金イベント記録",
)
def create_withdrawal(
    request: WithdrawalCreate,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> WithdrawalResponse:
    """
    出金 tx を transactions テーブルに記録する。

    フロー:
    1. ユーザーが Privy 本人鍵で USDC.transfer を署名 → tx 発火
    2. tx_hash 取得後、本エンドポイントを呼んでバックエンドに記録
    3. backend はオンチェーン送金には関与しない (記録のみ)

    重複防止: 同一 tx_hash の二重登録は 409 で拒否する。
    """
    # 重複チェック
    existing = db.execute(
        select(Transaction).where(Transaction.tx_hash == request.tx_hash)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Withdrawal with tx_hash {request.tx_hash} already recorded",
        )

    # transactions テーブルに記録
    # operation="withdraw" / asset="USDC" / amount_usd は amount と同値 (USDC は USD ペッグ前提)
    tx = Transaction(
        user_id=current_user.id,
        wallet_address=request.to_address,
        operation="withdraw",
        asset="USDC",
        amount=request.amount_usdc,
        amount_usd=request.amount_usdc,
        tx_hash=request.tx_hash,
        chain=request.network,
        status="completed",
        is_dry_run=False,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    logger.info(
        "User %s recorded withdrawal: %s USDC to %s (tx=%s)",
        current_user.email,
        request.amount_usdc,
        request.to_address,
        request.tx_hash,
    )

    return WithdrawalResponse(
        id=tx.id,
        user_id=tx.user_id,
        tx_hash=tx.tx_hash or "",
        to_address=tx.wallet_address or "",
        amount_usdc=tx.amount,
        network=tx.chain,
        status=tx.status,
        created_at=tx.created_at,
    )


@router.get(
    "",
    response_model=WithdrawalListResponse,
    summary="出金履歴取得",
)
def list_withdrawals(
    limit: int = 50,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> WithdrawalListResponse:
    """自分の出金履歴を新しい順に返す。"""
    if limit <= 0 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be 1..200",
        )

    stmt = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .where(Transaction.operation == "withdraw")
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()

    items = [
        WithdrawalResponse(
            id=tx.id,
            user_id=tx.user_id,
            tx_hash=tx.tx_hash or "",
            to_address=tx.wallet_address or "",
            amount_usdc=tx.amount,
            network=tx.chain,
            status=tx.status,
            created_at=tx.created_at,
        )
        for tx in rows
    ]
    return WithdrawalListResponse(items=items, total=len(items))
