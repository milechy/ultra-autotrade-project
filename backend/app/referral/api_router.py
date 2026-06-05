# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/api_router.py
"""Lane C1: /api/referral/* エンドポイント (全 active user 対象)。

partner-only の /partner/referral/* と異なり、role に関わらず
認証済みの active user であれば利用できる。

  - POST /api/referral/code      紹介コード取得 (未発行なら発行)
  - GET  /api/referral/earnings  紹介情報サマリー (LIFF 紹介パネル用)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

from . import service
from .schemas import ReferralCodeResponse, ReferralInfoResponse

router = APIRouter(prefix="/api/referral", tags=["referral-api"])


@router.post(
    "/code",
    response_model=ReferralCodeResponse,
    summary="紹介コード取得/発行 (全 active user)",
)
def post_api_referral_code(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ReferralCodeResponse:
    """認証済み active user の紹介コードを取得する。未発行なら自動発行する。"""
    code = service.get_or_create_code(db, current_user)
    return ReferralCodeResponse(
        referral_code=code,
        share_url=service.build_share_url(code),
    )


@router.get(
    "/earnings",
    response_model=ReferralInfoResponse,
    summary="紹介情報サマリー (LIFF 紹介パネル用)",
)
def get_api_referral_earnings(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ReferralInfoResponse:
    """紹介コード・人数・報酬・紹介済みユーザー一覧を返す。"""
    data = service.get_api_referral_info(db, current_user)
    return ReferralInfoResponse(**data)
