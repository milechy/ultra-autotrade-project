# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/router.py
"""RAS Lane 2 ルーター。

partner-only エンドポイント (admin / user は 403):
  - POST /referral/code                            紹介コード取得 (未発行なら発行)
  - GET  /referral/list                            配下ユーザー一覧
  - GET  /referral/users/{user_id}/transactions    配下ユーザーの取引履歴
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User, UserRole
from app.database import get_db
from app.transactions.models import Transaction

from . import service
from .schemas import (
    ReferralCodeResponse,
    ReferralTransactionResponse,
    ReferredUserResponse,
)

router = APIRouter(prefix="/referral", tags=["referral"])


def require_partner_only(
    user: User = Depends(require_active_user),
) -> User:
    """RAS 専用 RBAC: ``role == PARTNER`` のみ許可。

    既存 ``require_partner`` は admin も通すが、紹介プログラムは partner 固有のため
    admin / 一般ユーザーはいずれも 403 を返す。
    """
    if user.role != UserRole.PARTNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner role required",
        )
    return user


@router.post(
    "/code",
    response_model=ReferralCodeResponse,
    summary="紹介コード取得 (partner 専用、未発行なら発行)",
)
def post_referral_code(
    current_user: User = Depends(require_partner_only),
    db: Session = Depends(get_db),
) -> ReferralCodeResponse:
    """partner の紹介コードを取得する。未発行なら自動発行する。"""
    code = service.get_or_create_code(db, current_user)
    return ReferralCodeResponse(
        referral_code=code,
        share_url=service.build_share_url(code),
    )


@router.get(
    "/list",
    response_model=list[ReferredUserResponse],
    summary="紹介経由で登録されたユーザー一覧 (partner 専用)",
)
def get_referral_list(
    current_user: User = Depends(require_partner_only),
    db: Session = Depends(get_db),
) -> list[ReferredUserResponse]:
    """partner 配下のユーザー一覧を返す (email はマスクして返却)。"""
    referred_users = service.list_referred_users(db, current_user.id)
    return [
        ReferredUserResponse(
            id=u.id,
            email_masked=service.mask_email(u.email),
            role=u.role,
            created_at=u.created_at,
        )
        for u in referred_users
    ]


@router.get(
    "/users/{user_id}/transactions",
    response_model=list[ReferralTransactionResponse],
    summary="配下ユーザーの取引履歴 (partner 専用、wallet/tx は含まない)",
)
def get_referral_transactions(
    user_id: int,
    current_user: User = Depends(require_partner_only),
    db: Session = Depends(get_db),
) -> list[ReferralTransactionResponse]:
    """配下ユーザーの取引履歴を返す。

    - operation が deposit / withdraw / borrow / repay のもののみ
    - wallet_address / tx_hash はレスポンスに含めない (法務未クリア)
    """
    txs: list[Transaction] = service.list_transactions(db, current_user.id, user_id)
    return [
        ReferralTransactionResponse(
            # service.list_transactions が _ALLOWED_TX_TYPES でフィルタ済み。
            type=tx.operation,
            amount=str(tx.amount),
            occurred_at=tx.created_at,
        )
        for tx in txs
    ]
