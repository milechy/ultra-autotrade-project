# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/router.py
"""パートナー統計 API ルーター定義。

GET /api/partner/stats                    — 配下ユーザー全体の KPI（require_partner）
GET /api/partner/users/{user_id}/stats    — 特定ユーザーの運用実績（require_partner）
GET /api/partner/monthly                  — 月別運用実績集計（require_partner）
GET /api/partner/notifications            — 自パートナー向け通知ログ（require_partner）
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_partner
from app.auth.models import User
from app.database import get_db
from app.notifications.models import NotificationLog

from . import service
from .schemas import (
    MonthlyStatsResponse,
    NotificationLogItem,
    NotificationLogPage,
    PartnerStatsResponse,
    TesterItem,
    UserStatsResponse,
)

router = APIRouter(prefix="/api/partner", tags=["partner"])


@router.get(
    "/testers",
    response_model=list[TesterItem],
    summary="パートナーが招待したテスター一覧",
)
def get_testers(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> list[TesterItem]:
    """パートナーが招待した（invited_by = 自分のID）アクティブユーザー一覧を返す。"""
    users = (
        db.query(User)
        .filter(User.invited_by == current_user.id, User.is_active.is_(True))
        .order_by(User.created_at.desc())
        .all()
    )
    return [TesterItem.model_validate(u) for u in users]


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


@router.get(
    "/notifications",
    response_model=NotificationLogPage,
    summary="パートナー向け通知ログ一覧",
)
def get_partner_notifications(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
    severity: Optional[str] = Query(
        default=None, description="フィルタ: info/warning/alert/emergency"
    ),
    page: int = Query(default=1, ge=1, description="ページ番号（1始まり）"),
    per_page: int = Query(default=20, ge=1, le=100, description="1ページあたりの件数"),
) -> NotificationLogPage:
    """自パートナー宛の通知ログを返す（partner_id = 自分のID）。

    partner_id が NULL の通知（システム全体向け）は含まない。
    """
    query = db.query(NotificationLog).filter(NotificationLog.partner_id == current_user.id)
    if severity:
        query = query.filter(NotificationLog.severity == severity)

    total: int = query.with_entities(func.count(NotificationLog.id)).scalar() or 0
    logs = (
        query.order_by(desc(NotificationLog.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return NotificationLogPage(
        items=[NotificationLogItem.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
    )
