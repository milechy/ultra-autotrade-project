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
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.database import get_db

from .dependencies import require_active_user, require_admin
from .models import (
    PARTNER_ONLY_RISK_MODES,
    PHASE_1_ALLOWED_RISK_MODES,
    RISK_MODE_JP_LABELS,
    RISK_MODE_PHASE,
    RISK_MODE_PROTOCOLS,
    RISK_MODE_SUBSCRIPTION_RATES,
    AuditLog,
    RiskMode,
    User,
    UserRole,
)
from .schemas import (
    AuditLogEntry,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    RegisterResponse,
    RiskModeUpdateRequest,
    TermsAcceptRequest,
    TermsStatusResponse,
    TokenResponse,
    UserResponse,
    WalletConnectRequest,
    WalletConnectResponse,
)
from .service import AuthService

limiter = Limiter(key_func=get_remote_address)

LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/minute")

CURRENT_TERMS_VERSION = "2.0"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initial admin registration or invitation-based registration",
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """
    Register a user.

    - With invitation_code: register as viewer via partner invitation.
    - Without invitation_code: initial admin registration (first user only).
    """
    if request.invitation_code:
        from app.invitations import service as invitation_service  # noqa: PLC0415

        invitation = invitation_service.validate_code(db, request.invitation_code)
        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invitation code",
            )
        try:
            user = AuthService.create_user(db, request, role=UserRole.VIEWER.value)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        # Record which partner invited this user (supports multi-use codes)
        user.invited_by = invitation.partner_id
        db.commit()
        db.refresh(user)
        invitation_service.increment_usage(db, invitation, user_id=user.id)
        logger.info(
            "User registered via invitation: %s (partner_id=%d)", user.email, invitation.partner_id
        )
        token, expires_in = AuthService.create_access_token(user.id, user.email, user.role)
        return RegisterResponse(
            **UserResponse.model_validate(user).model_dump(),
            access_token=token,
            expires_in=expires_in,
        )

    # Initial admin registration (no invitation code)
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
        token, expires_in = AuthService.create_access_token(user.id, user.email, user.role)
        return RegisterResponse(
            **UserResponse.model_validate(user).model_dump(),
            access_token=token,
            expires_in=expires_in,
        )
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
    current_value = user.risk_mode or "conservative"
    try:
        current_enum = RiskMode(current_value)
        current_label = RISK_MODE_JP_LABELS[current_enum]
    except ValueError:
        current_label = RISK_MODE_JP_LABELS[RiskMode.CONSERVATIVE]
    return {
        "mode": current_value,
        "label": current_label,
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
    """Update the user's risk mode.

    Phase 1 では CONSERVATIVE のみ許可 (BALANCED / AGGRESSIVE は 403)。
    CUSTOM は partner / admin のみ許可 (Phase 1 から利用可能)。
    """
    try:
        new_mode = RiskMode(request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown risk_mode: {request.mode!r}",
        ) from exc

    # CUSTOM モード: partner/admin 限定 + custom_params 必須
    if new_mode in PARTNER_ONLY_RISK_MODES:
        if user.role not in (UserRole.ADMIN.value, UserRole.PARTNER.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="カスタムモードはパートナー専用です。",
            )
        if request.custom_params is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="カスタムモード選択時は custom_params が必要です。",
            )
    # 通常モード: Phase 1 制限
    elif new_mode not in PHASE_1_ALLOWED_RISK_MODES:
        jp_label = RISK_MODE_JP_LABELS[new_mode]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{jp_label}はPhase 2以降で利用可能です。",
        )

    old_mode = user.risk_mode
    user.risk_mode = new_mode.value

    if new_mode in PARTNER_ONLY_RISK_MODES and request.custom_params is not None:
        user.custom_risk_params = request.custom_params.model_dump()
    elif new_mode not in PARTNER_ONLY_RISK_MODES:
        user.custom_risk_params = None

    # 監査ログ記録 (CUSTOM モード変更時)
    if new_mode in PARTNER_ONLY_RISK_MODES or (
        old_mode and RiskMode(old_mode) in PARTNER_ONLY_RISK_MODES
    ):
        audit_entry = AuditLog(
            user_id=user.id,
            actor_id=user.id,
            action="risk_mode_change",
            old_value=old_mode,
            new_value=new_mode.value,
        )
        db.add(audit_entry)

    db.commit()
    db.refresh(user)
    logger.info("User changed risk mode to %s: %s", new_mode.value, user.email)
    return {
        "mode": user.risk_mode,
        "label": RISK_MODE_JP_LABELS[new_mode],
        "message": f"Risk mode updated to {new_mode.value}",
    }


@router.get(
    "/risk-modes",
    summary="List all risk modes (with labels, phase, allow status)",
)
def list_risk_modes(
    user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """全リスクモード一覧を返す (フロント側のモード選択 UI 用)。

    CUSTOM モードは partner/admin のみに表示する。

    Returns:
        ``{"modes": [{mode, label, phase, allowed_in_phase_1, subscription_rate, protocols, partner_only}, ...]}``
    """
    is_partner_or_admin = user.role in (UserRole.ADMIN.value, UserRole.PARTNER.value)
    modes_payload = []
    for mode in RiskMode:
        if mode in PARTNER_ONLY_RISK_MODES and not is_partner_or_admin:
            continue
        modes_payload.append(
            {
                "mode": mode.value,
                "label": RISK_MODE_JP_LABELS[mode],
                "phase": RISK_MODE_PHASE[mode],
                "allowed_in_phase_1": mode in PHASE_1_ALLOWED_RISK_MODES,
                "subscription_rate": str(RISK_MODE_SUBSCRIPTION_RATES[mode]),
                "protocols": sorted(RISK_MODE_PROTOCOLS[mode]),
                "partner_only": mode in PARTNER_ONLY_RISK_MODES,
            }
        )
    return {"modes": modes_payload}


@router.get(
    "/admin/risk-modes/custom-audit",
    summary="List CUSTOM risk mode change audit log (admin only)",
)
def list_custom_risk_mode_audit(
    limit: int = 50,
    offset: int = 0,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """CUSTOM リスクモード変更の監査ログ一覧を返す (admin 専用)。

    Returns:
        ``{"entries": [...], "total": int}``
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    total_row = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "risk_mode_change")
    ).scalar_one()

    rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.action == "risk_mode_change")
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    # user_id / actor_id → email のルックアップ
    user_ids = {r.user_id for r in rows} | {r.actor_id for r in rows if r.actor_id}
    users_map: dict[int, str] = {}
    if user_ids:
        user_rows = db.execute(select(User.id, User.email).where(User.id.in_(user_ids))).all()
        users_map = {row.id: row.email for row in user_rows}

    entries = [
        AuditLogEntry(
            id=row.id,
            user_id=row.user_id,
            actor_id=row.actor_id,
            action=row.action,
            old_value=row.old_value,
            new_value=row.new_value,
            created_at=row.created_at,
            user_email=users_map.get(row.user_id),
            actor_email=users_map.get(row.actor_id) if row.actor_id else None,
        )
        for row in rows
    ]

    return {"entries": [e.model_dump() for e in entries], "total": total_row}


@router.post(
    "/wallet/connect",
    response_model=WalletConnectResponse,
    summary="WalletConnect authentication",
)
def wallet_connect(
    request: WalletConnectRequest,
    db: Session = Depends(get_db),
) -> WalletConnectResponse:
    """
    WalletConnectによる認証。初回接続時はユーザーを自動作成。

    1. 署名検証 (eth_account)
    2. ウォレットアドレスでユーザー検索
    3. 未登録なら自動登録（role=viewer, risk_mode=conservative）
    4. JWT発行
    """
    # 署名検証
    if not AuthService.verify_wallet_signature(
        request.wallet_address, request.message, request.signature
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid wallet signature",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ウォレットアドレスでユーザー検索
    existing_user = AuthService.get_user_by_wallet(db, request.wallet_address)
    is_new_user = existing_user is None

    if is_new_user:
        user = AuthService.create_wallet_user(db, request.wallet_address)
    else:
        if existing_user is None:
            raise RuntimeError("existing_user is None after wallet lookup")
        user = existing_user

    token, expires_in = AuthService.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )

    needs_terms_acceptance = user.terms_version != CURRENT_TERMS_VERSION

    logger.info(
        "Wallet connect: %s...%s (new=%s)",
        request.wallet_address[:10],
        request.wallet_address[-4:],
        is_new_user,
    )
    return WalletConnectResponse(
        access_token=token,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
        is_new_user=is_new_user,
        needs_terms_acceptance=needs_terms_acceptance,
    )


# ── LINE LIFF認証 ────────────────────────────────────────────────────────────


class LineAuthRequest(BaseModel):
    id_token: str
    display_name: str


@router.post("/line", response_model=TokenResponse, summary="LINE LIFF認証")
async def line_auth(
    request: LineAuthRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    LINE idTokenを検証してJWTを返す。
    LIFFアプリからのログインに使用する。
    """
    from .line import LineAuthError, get_or_create_line_user, verify_line_id_token  # noqa: PLC0415

    try:
        payload = await verify_line_id_token(request.id_token)
    except LineAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    line_user_id: str = payload["sub"]
    display_name: str = payload.get("name", request.display_name)

    user = get_or_create_line_user(db, line_user_id, display_name)
    token, expires_in = AuthService.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
    )
