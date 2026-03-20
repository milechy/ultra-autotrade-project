# backend/app/auth/router.py
"""
認証 API エンドポイント。

POST /auth/register - 初回管理者登録
POST /auth/login    - ログイン
POST /auth/logout   - ログアウト（フロントエンド側でトークン破棄）
GET  /auth/me       - 現在のユーザー情報取得
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db

from .dependencies import require_active_user
from .models import User, UserRole
from .schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    RiskModeUpdateRequest,
    TermsAcceptRequest,
    TermsStatusResponse,
    TokenResponse,
    UserResponse,
)
from .service import AuthService

CURRENT_TERMS_VERSION = "2.0"

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
    # INITIAL_ADMIN_EMAIL が未設定なら登録不可
    initial_admin_email = os.getenv("INITIAL_ADMIN_EMAIL")
    if not initial_admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. INITIAL_ADMIN_EMAIL is not configured.",
        )
    if request.email != initial_admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Please contact an administrator.",
        )

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
        token_type="bearer",  # noqa: S106
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


@router.get(
    "/terms/status",
    response_model=TermsStatusResponse,
    summary="利用規約同意状態確認",
)
def get_terms_status(
    user: User = Depends(require_active_user),
) -> TermsStatusResponse:
    """現在のユーザーが最新の利用規約に同意済みかを確認する。"""
    return TermsStatusResponse(
        accepted=user.terms_version == CURRENT_TERMS_VERSION,
        terms_version=user.terms_version,
        terms_accepted_at=user.terms_accepted_at,
        current_version=CURRENT_TERMS_VERSION,
        needs_acceptance=user.terms_version != CURRENT_TERMS_VERSION,
    )


@router.post(
    "/terms/accept",
    response_model=TermsStatusResponse,
    summary="利用規約に同意",
)
def accept_terms(
    request: TermsAcceptRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> TermsStatusResponse:
    """利用規約に同意する。バージョンとタイムスタンプをDBに記録する。"""
    user.terms_accepted_at = datetime.now(timezone.utc)
    user.terms_version = request.version
    db.commit()
    db.refresh(user)
    logger.info("User accepted terms v%s: %s", request.version, user.email)
    return TermsStatusResponse(
        accepted=True,
        terms_version=user.terms_version,
        terms_accepted_at=user.terms_accepted_at,
        current_version=CURRENT_TERMS_VERSION,
        needs_acceptance=False,
    )


_RISK_OPTIONS = [
    {
        "mode": "conservative",
        "label": "保守（初心者向け）",
        "description": "低頻度・ステーブルコインのみ。安全重視。",
        "max_utilization": 60,
        "min_health_factor": "2.0",
        "allowed_assets": ["USDC", "USDT", "DAI"],
        "min_confidence": 80,
    },
    {
        "mode": "balanced",
        "label": "バランス（標準）",
        "description": "標準頻度。ステーブル＋ETHで運用。",
        "max_utilization": 75,
        "min_health_factor": "1.7",
        "allowed_assets": ["USDC", "USDT", "DAI", "ETH", "WBTC"],
        "min_confidence": 65,
    },
    {
        "mode": "aggressive",
        "label": "積極（経験者向け）",
        "description": "高頻度・多様な資産。リスク許容度が高い方向け。",
        "max_utilization": 90,
        "min_health_factor": "1.5",
        "allowed_assets": ["USDC", "USDT", "DAI", "ETH", "WBTC", "MATIC", "LINK"],
        "min_confidence": 50,
    },
]


@router.get(
    "/risk-mode",
    summary="リスクモード取得",
)
def get_risk_mode(
    user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """現在のユーザーのリスクモードと選択肢を返す。"""
    return {
        "mode": user.risk_mode or "conservative",
        "options": _RISK_OPTIONS,
    }


@router.put(
    "/risk-mode",
    summary="リスクモード変更",
)
def update_risk_mode(
    request: RiskModeUpdateRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """ユーザーのリスクモードを変更する（conservative / balanced / aggressive）。"""
    user.risk_mode = request.mode
    db.commit()
    db.refresh(user)
    logger.info("User changed risk mode to %s: %s", request.mode, user.email)
    return {"mode": user.risk_mode, "message": f"Risk mode updated to {request.mode}"}
