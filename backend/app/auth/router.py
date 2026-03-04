# backend/app/auth/router.py
"""
認証 API エンドポイント。

POST /auth/register - 初回管理者登録
POST /auth/login    - ログイン
POST /auth/logout   - ログアウト（フロントエンド側でトークン破棄）
GET  /auth/me       - 現在のユーザー情報取得
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db

from .dependencies import require_active_user
from .models import User, UserRole
from .schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from .service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="初回管理者登録",
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    初回管理者アカウントを登録する。

    既にユーザーが存在する場合は 403 エラーを返す。
    初回登録のみ許可し、以降は管理者が /users エンドポイントで作成する。
    """
    if AuthService.user_exists(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Please contact an administrator.",
        )

    try:
        user = AuthService.create_user(
            db,
            request,
            role=UserRole.ADMIN.value,  # 初回登録は常に管理者
        )
        logger.info("Initial admin registered: %s", user.email)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="ログイン",
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    ログインして JWT トークンを取得する。
    """
    user = AuthService.authenticate_user(db, request.email, request.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = AuthService.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )

    logger.info("User logged in: %s", user.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="ログアウト",
)
def logout(
    user: User = Depends(require_active_user),
) -> None:
    """
    ログアウトする。

    サーバー側ではトークンの無効化は行わない（ステートレス）。
    クライアント側でトークンを破棄する。
    """
    logger.info("User logged out: %s", user.email)
    return None


@router.get(
    "/me",
    response_model=UserResponse,
    summary="現在のユーザー情報取得",
)
def get_me(
    user: User = Depends(require_active_user),
) -> UserResponse:
    """
    現在ログイン中のユーザー情報を取得する。
    """
    return UserResponse.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="パスワード変更",
)
def change_password(
    request: PasswordChangeRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    自分のパスワードを変更する。
    """
    # 現在のパスワードを確認
    if not AuthService.verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # 新しいパスワードを設定
    AuthService.update_user(db, user, password=request.new_password)
    logger.info("User changed password: %s", user.email)
    return None
