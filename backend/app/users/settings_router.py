# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_router.py
"""ユーザー設定API ルーター定義。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

from .settings_schemas import UserSettingsResponse, UserSettingsUpdate

router = APIRouter(prefix="/api/user", tags=["user-settings"])


@router.get("/settings", response_model=UserSettingsResponse, summary="設定取得")
def get_user_settings(
    current_user: User = Depends(require_active_user),
) -> UserSettingsResponse:
    """現在のユーザー設定を返す。"""
    return UserSettingsResponse.model_validate(current_user)


@router.put("/settings", response_model=UserSettingsResponse, summary="設定更新")
def update_user_settings(
    request: UserSettingsUpdate,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    """ユーザー設定を更新する。"""
    if request.notification_frequency is not None:
        if request.notification_frequency not in ("all", "important", "none"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="notification_frequency must be one of: all, important, none",
            )
        current_user.notification_frequency = request.notification_frequency
    if request.notification_email is not None:
        current_user.notification_email = request.notification_email
    if request.max_single_trade_usd is not None:
        if request.max_single_trade_usd <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="max_single_trade_usd must be positive",
            )
        current_user.max_single_trade_usd = request.max_single_trade_usd
    if request.max_daily_trade_usd is not None:
        if request.max_daily_trade_usd <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="max_daily_trade_usd must be positive",
            )
        current_user.max_daily_trade_usd = request.max_daily_trade_usd
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserSettingsResponse.model_validate(current_user)


@router.post("/pause", summary="運用一時停止")
def pause_user(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """運用を一時停止する（is_active=False）。"""
    current_user.is_active = False
    db.add(current_user)
    db.commit()
    return {"message": "paused", "is_active": False}


@router.post("/resume", summary="運用再開")
def resume_user(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """運用を再開する（is_active=True）。"""
    current_user.is_active = True
    db.add(current_user)
    db.commit()
    return {"message": "resumed", "is_active": True}
