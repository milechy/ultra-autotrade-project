# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/router.py
"""
Authentication API endpoints.

POST /auth/register - Initial admin registration
POST /auth/login    - Login
POST /auth/logout   - Logout (token discarded on the frontend side)
GET  /auth/me       - Retrieve current user information
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
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

limiter = Limiter(key_func=get_remote_address)

LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/minute")

CURRENT_TERMS_VERSION = "2.0"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initial admin registration",
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Register the initial admin account.

    Returns 403 if a user already exists.
    Only the first registration is allowed; subsequent users must be created via /users by an admin.
    """
    # Registration disabled if INITIAL_ADMIN_EMAIL is not configured
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
            role=UserRole.ADMIN.value,  # First registration is always admin
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
    summary="Login",
)
@limiter.limit(LOGIN_RATE_LIMIT)
def login(
    request: Request,
    credentials: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Log in and obtain a JWT token.
    """
    user = AuthService.authenticate_user(db, credentials.email, credentials.password)

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
    summary="Logout",
)
def logout(
    user: User = Depends(require_active_user),
) -> None:
    """
    Log out.

    Token invalidation is not performed server-side (stateless).
    The client is responsible for discarding the token.
    """
    logger.info("User logged out: %s", user.email)
    return None


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user information",
)
def get_me(
    user: User = Depends(require_active_user),
) -> UserResponse:
    """
    Retrieve the currently authenticated user's information.
    """
    return UserResponse.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
)
def change_password(
    request: PasswordChangeRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Change the current user's password.
    """
    # Verify current password
    if not AuthService.verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Set new password
    AuthService.update_user(db, user, password=request.new_password)
    logger.info("User changed password: %s", user.email)
    return None


@router.get(
    "/terms/status",
    response_model=TermsStatusResponse,
    summary="Check terms acceptance status",
)
def get_terms_status(
    user: User = Depends(require_active_user),
) -> TermsStatusResponse:
    """Check whether the current user has accepted the latest terms of service."""
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
    summary="Accept terms of service",
)
def accept_terms(
    request: TermsAcceptRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> TermsStatusResponse:
    """Accept the terms of service. Records version and timestamp in the DB."""
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
    summary="Get risk mode",
)
def get_risk_mode(
    user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """Return the current user's risk mode and available options."""
    return {
        "mode": user.risk_mode or "conservative",
        "options": _RISK_OPTIONS,
    }


@router.put(
    "/risk-mode",
    summary="Update risk mode",
)
def update_risk_mode(
    request: RiskModeUpdateRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update the user's risk mode (conservative / balanced / aggressive)."""
    user.risk_mode = request.mode
    db.commit()
    db.refresh(user)
    logger.info("User changed risk mode to %s: %s", request.mode, user.email)
    return {"mode": user.risk_mode, "message": f"Risk mode updated to {request.mode}"}
