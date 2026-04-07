# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/router.py
"""パートナー統計 API ルーター定義。

GET /api/partner/stats             — 配下ユーザー全体の KPI（require_partner）
GET /api/partner/users/{user_id}/stats — 特定ユーザーの運用実績（require_partner）
GET /api/partner/monthly           — 月別運用実績集計（require_partner）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

from . import service
from .schemas import MonthlyStatsResponse, PartnerStatsResponse, UserStatsResponse

router = APIRouter(prefix="/api/partner", tags=["partner"])

_PARTNER_ROLES = ("partner", "admin")


async def require_partner(user: User = Depends(require_active_user)) -> User:
    """
    partner または admin ロールを要求する。

    Note: Wave 1 で auth/dependencies.py に追加予定。
    それまでの間はここで定義する。
    """
    if user.role not in _PARTNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner or admin access required",
        )
    return user


@router.get(
    "/stats",
    response_model=PartnerStatsResponse,
    summary="パートナー配下ユーザー全体の KPI",
)
def get_partner_stats(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> PartnerStatsResponse:
    """パートナーが招待したユーザー全体の AUM・利回りを返す。"""
    return service.get_partner_stats(db, current_user.id)


@router.get(
    "/users/{user_id}/stats",
    response_model=UserStatsResponse,
    summary="特定ユーザーの運用実績",
)
def get_user_stats(
    user_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> UserStatsResponse:
    """パートナーが招待した特定ユーザーの運用実績を返す。"""
    try:
        return service.get_user_stats(db, current_user.id, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/monthly",
    response_model=list[MonthlyStatsResponse],
    summary="月別運用実績集計",
)
def get_monthly_stats(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> list[MonthlyStatsResponse]:
    """パートナー配下ユーザーの月別 AUM・利回りを返す。"""
    return service.get_monthly_stats(db, current_user.id)
