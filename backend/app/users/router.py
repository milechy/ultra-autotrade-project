# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/router.py
"""
ユーザー管理 API エンドポイント。

GET    /users         - ユーザー一覧（admin: 全件 / partner: 招待ユーザーのみ）
POST   /users         - ユーザー作成（admin のみ）
GET    /users/{id}    - ユーザー詳細（自分または admin）
PUT    /users/{id}    - ユーザー更新（自分または admin）
DELETE /users/{id}    - ユーザー削除（admin のみ、自分自身は削除不可）
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin, require_partner
from app.auth.models import User
from app.auth.schemas import (
    UserCreateRequest,
    UserResponse,
    UserRole,
    UserUpdateRequest,
)
from app.auth.service import AuthService
from app.database import get_db
from app.users.fee_service import FeeRateRange, get_fee_rate_range, get_full_fee_schedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=List[UserResponse],
    summary="ユーザー一覧取得",
)
def list_users(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> List[UserResponse]:
    """
    ユーザーの一覧を取得する。

    - admin: 全ユーザーを返す
    - partner: 自分が招待したユーザーのみ返す
    """
    if current_user.role == UserRole.PARTNER.value:
        users = db.query(User).filter(User.invited_by == current_user.id).all()
    else:
        users = AuthService.get_all_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ユーザー作成",
)
def create_user(
    request: UserCreateRequest,
    admin: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    新しいユーザーを作成する。

    - admin: 全ロール作成可能
    - partner: viewer のみ作成可能（権限昇格防止）
    """
    # partner は viewer のみ作成可能（admin/editor/partner は作成不可）
    if admin.role == UserRole.PARTNER.value and request.role != UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner can only create viewer users",
        )
    try:
        user = AuthService.create_user(db, request)
        logger.info("%s %s created user: %s", admin.role, admin.email, user.email)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


class FeeScheduleResponse(BaseModel):
    """手数料体系レスポンス。"""

    schedule: list[FeeRateRange]
    note: str


class UserFeeInfoResponse(BaseModel):
    """指定ユーザーのティア + 手数料率レンジレスポンス。"""

    user_id: int
    tier: str
    fee_rate_range: FeeRateRange


@router.get(
    "/fee-schedule",
    response_model=FeeScheduleResponse,
    summary="ティア別手数料体系取得",
)
def get_fee_schedule(
    current_user: User = Depends(require_partner),
) -> FeeScheduleResponse:
    """
    全ティアの手数料率レンジ一覧を返す。

    - partner / admin: アクセス可能
    """
    return FeeScheduleResponse(
        schedule=get_full_fee_schedule(),
        note="手数料率はAIの判定精度に応じて動的に決定されます",
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="ユーザー詳細取得",
)
def get_user(
    user_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    指定したユーザーの詳細を取得する。

    自分自身または管理者のみアクセス可能。
    """
    # 自分自身または管理者かチェック
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="ユーザー更新",
)
def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    指定したユーザーを更新する。

    - 自分自身または管理者: 全フィールド変更可能（role/is_active は管理者のみ）
    - パートナー: 自分が招待したユーザー（invited_by == self.id）の
      email/username/password/is_active を変更可能。role 変更は不可。
    """
    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # パートナーが自分の招待テスターを編集するケースを許可
    is_partner_editing_own_tester = (
        current_user.role == UserRole.PARTNER.value and user.invited_by == current_user.id
    )

    if (
        current_user.id != user_id
        and not current_user.is_admin
        and not is_partner_editing_own_tester
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    role = request.role.value if request.role else None
    is_active = request.is_active

    if not current_user.is_admin:
        # role 変更は admin 専用
        if role is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change role",
            )
        # is_active 変更はパートナーが自分のテスターに対してのみ許可
        if is_active is not None and not is_partner_editing_own_tester:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change active status",
            )

    # 最後の admin を降格または無効化できない
    if user.is_admin and AuthService.count_admins(db) <= 1:
        # ロールを viewer に変更しようとしている場合
        if role is not None and role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last admin",
            )
        # is_active を False に変更しようとしている場合
        if is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last admin",
            )

    try:
        updated_user = AuthService.update_user(
            db,
            user,
            email=request.email,
            username=request.username,
            password=request.password,
            role=role,
            is_active=is_active,
        )
        logger.info("User %s updated user: %s", current_user.email, updated_user.email)
        return UserResponse.model_validate(updated_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="ユーザー削除",
)
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """
    指定したユーザーを削除する。

    管理者のみアクセス可能。
    自分自身は削除できない。
    最後の管理者は削除できない。
    """
    # 自分自身は削除できない
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # 最後の管理者は削除できない
    if user.is_admin and AuthService.count_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last admin",
        )

    AuthService.delete_user(db, user)
    logger.info("Admin %s deleted user: %s", admin.email, user.email)
    return None


class TierResponse(BaseModel):
    """ユーザーティア情報レスポンス。"""

    user_id: int
    tier: str


@router.get(
    "/{user_id}/tier",
    response_model=TierResponse,
    summary="ユーザーティア取得",
)
def get_user_tier(
    user_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> TierResponse:
    """
    指定ユーザーの投資ティアを返す。

    - partner: 自分が招待したユーザー（または自分自身）のみ参照可能
    - admin: 全ユーザー参照可能
    """
    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not current_user.is_admin:
        is_own = current_user.id == user_id
        is_own_tester = user.invited_by == current_user.id
        if not is_own and not is_own_tester:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    return TierResponse(user_id=user_id, tier=user.tier)


@router.get(
    "/{user_id}/fee-info",
    response_model=UserFeeInfoResponse,
    summary="指定ユーザーのティア別手数料情報取得",
)
def get_user_fee_info(
    user_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> UserFeeInfoResponse:
    """
    指定ユーザーのティアと対応する手数料率レンジを返す。

    - partner: 自分が招待したユーザー（または自分自身）のみ参照可能
    - admin: 全ユーザー参照可能
    """
    user = AuthService.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not current_user.is_admin:
        is_own = current_user.id == user_id
        is_own_tester = user.invited_by == current_user.id
        if not is_own and not is_own_tester:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    fee_range = get_fee_rate_range(user.tier)
    return UserFeeInfoResponse(user_id=user_id, tier=user.tier, fee_rate_range=fee_range)
