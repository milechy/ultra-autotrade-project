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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.referral import service as referral_service

from .dependencies import require_active_user, require_admin
from .models import (
    PHASE_1_ALLOWED_RISK_MODES,
    RISK_MODE_JP_LABELS,
    RISK_MODE_PHASE,
    RISK_MODE_PROTOCOLS,
    RISK_MODE_SUBSCRIPTION_RATES,
    RiskMode,
    User,
    UserRole,
)
from .privy_verifier import get_privy_verifier
from .schemas import (
    LoginRequest,
    OpenRegisterRequest,
    PasswordChangeRequest,
    RegisterRequest,
    RegisterResponse,
    RegisterWithReferralRequest,
    RiskModeUpdateRequest,
    TermsAcceptRequest,
    TermsStatusResponse,
    TokenResponse,
    UserResponse,
    WalletConnectRequest,
    WalletConnectResponse,
    WalletLinkRequest,
    WalletLinkResponse,
)
from .service import AuthService

limiter = Limiter(key_func=get_remote_address)

LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/minute")

CURRENT_TERMS_VERSION = "2.0"
# LIFF 固有の同意バージョン（liff-confirm 経由での同意）も accepted として扱う
_LIFF_TERMS_VERSION = "liff-v3"
_ACCEPTED_TERMS_VERSIONS = frozenset([CURRENT_TERMS_VERSION, _LIFF_TERMS_VERSION])

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
    - Without code: initial admin registration (first user only).
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
    "/register-with-referral",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Referral-based user registration (invitation-only signup)",
)
@limiter.limit(LOGIN_RATE_LIMIT)
def register_with_referral(
    request: Request,
    body: RegisterWithReferralRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """
    Register a new user via partner referral code.

    Validation order (per spec):
    1. referral_code format (8-char alphanumeric) — Pydantic 422
    2. referral_code DB lookup — 404
    3. referred_consent == true — 422
    4. email duplicate — 409
    5. create user (role=viewer fixed)
    6. set referrer_id + referred_consent_at
    7. issue JWT → 201
    """
    # Step 2: DB lookup
    referrer = db.query(User).filter(User.referral_code == body.referral_code).first()
    if referrer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="referral code not found",
        )

    # Step 3: consent check
    if not body.referred_consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="referral consent required",
        )

    # Step 4: email duplicate
    if AuthService.get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    # Step 5: create user (role=viewer, fixed)
    try:
        user = AuthService.create_user(db, body, role=UserRole.VIEWER.value)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Step 6: set referral fields + 紹介キャンペーン ウィンドウ作成
    user.referrer_id = referrer.id
    user.referred_consent_at = datetime.now(timezone.utc)
    referral_service.handle_new_referral(db, partner_id=referrer.id, referree_id=user.id)
    db.commit()
    db.refresh(user)

    logger.info(
        "User registered via referral: %s (referrer_id=%d, code=%s)",
        user.email,
        referrer.id,
        body.referral_code,
    )

    # Step 7: JWT
    token, expires_in = AuthService.create_access_token(user.id, user.email, user.role)
    return RegisterResponse(
        **UserResponse.model_validate(user).model_dump(),
        access_token=token,
        expires_in=expires_in,
    )


@router.post(
    "/register-open",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="一般登録（partner 招待不要）",
)
@limiter.limit(LOGIN_RATE_LIMIT)
def register_open(
    request: Request,
    body: OpenRegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """
    一般登録（open registration mode）。

    フロー:
    1. 利用規約同意確認 (terms_consent == True)
    2. [KYC ゲート接続点] — TODO: KYC 実装は別 Lane で追加予定
       # kyc_service.check(request.email) → KYC 未通過なら 403 で弾く予定
    3. Email/username 重複チェック
    4. ユーザー作成 (role=viewer)
    5. open 招待レコード作成（監査用・即使用済みマーク）
    6. JWT 発行 → 201

    利用規約はログイン後に GET /auth/terms/status で確認し、
    POST /auth/terms/accept で正式同意する（バージョン管理済み）。
    """
    if os.getenv("ENABLE_OPEN_REGISTRATION", "false").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # terms_consent フィールドバリデーターで False は既に 422 にしているが
    # 防御的に router 側でも確認する
    if not body.terms_consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="利用規約への同意が必要です",
        )

    # [KYC ゲート接続点] ─────────────────────────────────────────────
    # 実装予定: kyc_service.verify(request.email)
    #   - PENDING  → 202 (KYC審査中) または 403 (要KYC完了)
    #   - REJECTED → 403
    #   - APPROVED → 通過
    # ────────────────────────────────────────────────────────────────

    from datetime import timedelta  # noqa: PLC0415

    from app.invitations import service as invitation_service  # noqa: PLC0415

    try:
        user = AuthService.create_user(db, body, role=UserRole.VIEWER.value)
    except ValueError as e:
        detail = str(e)
        if "already registered" in detail or "already taken" in detail:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    user.terms_version = _LIFF_TERMS_VERSION
    user.terms_accepted_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)

    # open 招待レコードを監査用に作成（登録完了時点で即使用済み）
    open_inv = invitation_service.create_open_invitation(
        db,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        max_uses=1,
    )
    invitation_service.increment_usage(db, open_inv, user_id=user.id)

    logger.info("User registered via open registration: %s", user.email)
    token, expires_in = AuthService.create_access_token(user.id, user.email, user.role)
    return RegisterResponse(
        **UserResponse.model_validate(user).model_dump(),
        access_token=token,
        expires_in=expires_in,
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
    accepted = user.terms_version in _ACCEPTED_TERMS_VERSIONS
    return TermsStatusResponse(
        accepted=accepted,
        terms_version=user.terms_version,
        terms_accepted_at=user.terms_accepted_at,
        current_version=CURRENT_TERMS_VERSION,
        needs_acceptance=not accepted,
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
    """Update the user's risk mode (conservative / balanced / aggressive).

    Phase 1 では CONSERVATIVE のみ許可する (BALANCED / AGGRESSIVE は 403)。
    Phase 2 で ``PHASE_1_ALLOWED_RISK_MODES`` を拡張して解禁する。
    """
    # 内部値 (str) を enum に変換 (RiskModeUpdateRequest 側で pattern で制限済み)
    try:
        new_mode = RiskMode(request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown risk_mode: {request.mode!r}",
        ) from exc

    # Phase 1 制限: 許可されていないモードは 403
    if new_mode not in PHASE_1_ALLOWED_RISK_MODES:
        jp_label = RISK_MODE_JP_LABELS[new_mode]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{jp_label}はPhase 2以降で利用可能です。",
        )

    user.risk_mode = new_mode.value
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
    _user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """全リスクモード一覧を返す (フロント側のモード選択 UI 用)。

    Returns:
        ``{"modes": [{mode, label, phase, allowed_in_phase_1, subscription_rate, protocols}, ...]}``
    """
    modes_payload = []
    for mode in RiskMode:
        modes_payload.append(
            {
                "mode": mode.value,
                "label": RISK_MODE_JP_LABELS[mode],
                "phase": RISK_MODE_PHASE[mode],
                "allowed_in_phase_1": mode in PHASE_1_ALLOWED_RISK_MODES,
                "subscription_rate": str(RISK_MODE_SUBSCRIPTION_RATES[mode]),
                "protocols": sorted(RISK_MODE_PROTOCOLS[mode]),
            }
        )
    return {"modes": modes_payload}


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

    # ── Privy ID Token 検証 (Codex Review P1 対応) ──
    # 後方互換のため、PRIVY_APP_ID 未設定時 (= verifier=None) は privy_did/id_token を
    # 検証せずに drop する。本番環境では PRIVY_APP_ID + 公開鍵を必ず設定すること。
    verifier = get_privy_verifier()
    privy_did_to_store: str | None = None
    if verifier is None:
        # 後方互換モード: PRIVY_APP_ID 未設定時は Privy フィールドを silent drop して通常認証へ継続
        if request.privy_id_token or request.privy_did:
            logger.warning(
                "Privy verification disabled (PRIVY_APP_ID not set), "
                "dropping privy_id_token=%s and privy_did=%s",
                "<present>" if request.privy_id_token else None,
                "<present>" if request.privy_did else None,
            )
    elif request.privy_id_token:
        # 検証モード (PRIVY_APP_ID 設定済み): id_token を検証して DID を取得
        verified_did = verifier.verify_id_token(request.privy_id_token)
        if request.privy_did and request.privy_did != verified_did:
            logger.warning(
                "Privy DID mismatch: request.privy_did=%s..., id_token.sub=%s...",
                request.privy_did[:20],
                verified_did[:20],
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Privy DID does not match ID token sub",
            )
        privy_did_to_store = verified_did
    elif request.privy_did:
        # Privy 検証 ON 環境では未検証 DID を受け付けない
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="privy_did requires privy_id_token for verification",
        )

    # ウォレットアドレスでユーザー検索
    existing_user = AuthService.get_user_by_wallet(db, request.wallet_address)

    if existing_user is None:
        # 新規候補: create_wallet_user は並行 race を吸収して
        # 既存ユーザーを返す可能性があるため、is_new_user は戻り値の
        # is_newly_created に従う (lookup 時点の None だけで決定しない)。
        user, is_newly_created = AuthService.create_wallet_user(
            db, request.wallet_address, privy_did=privy_did_to_store
        )
        is_new_user = is_newly_created
    else:
        user = existing_user
        is_new_user = False
        # 既存ユーザーに privy_did が未保存かつ検証済み DID が手元にあれば後追い保存。
        # IntegrityError (= 別ユーザーが既に同じ DID を保持) は 409、
        # それ以外の DB エラーは 500 で明示的に返す。silently 握り潰さない。
        if privy_did_to_store and not user.privy_did:
            try:
                AuthService.update_privy_did(db, user, privy_did_to_store)
            except IntegrityError as exc:
                db.rollback()
                constraint_name = AuthService._extract_constraint_name(exc)
                if constraint_name and "privy_did" in constraint_name:
                    logger.warning(
                        "privy_did backfill conflict (DID already linked to another user): "
                        "wallet=%s..., did=%s...",
                        request.wallet_address[:10],
                        privy_did_to_store[:20],
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Privy DID already linked to another user",
                    ) from exc
                logger.exception(
                    "privy_did backfill failed with unexpected IntegrityError "
                    "(constraint=%s): wallet=%s...",
                    constraint_name or "<unknown>",
                    request.wallet_address[:10],
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="DID backfill failed",
                ) from exc
            except Exception as exc:
                db.rollback()
                logger.exception(
                    "privy_did backfill failed: wallet=%s...",
                    request.wallet_address[:10],
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="DID backfill failed",
                ) from exc

    token, expires_in = AuthService.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )

    needs_terms_acceptance = user.terms_version not in _ACCEPTED_TERMS_VERSIONS

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


@router.post(
    "/wallet/link",
    response_model=WalletLinkResponse,
    summary="認証済みユーザーにウォレットを紐付け (F-17 L1)",
)
def wallet_link(
    request: WalletLinkRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> WalletLinkResponse:
    """
    JWT で認証済みのユーザーに EVM ウォレットアドレスを紐付ける。

    レスポンス:
    - 200: 紐付け成功
    - 401: 未認証 (require_active_user が返す)
    - 422: 署名検証失敗
    - 409: 別ユーザーが同じ wallet_address をすでにリンク済み
    - 404: privy_did 不一致 (JWT ユーザーと wallet ユーザーが別人)
    """
    # 422: 署名検証
    if not AuthService.verify_wallet_signature(request.address, request.message, request.signature):
        logger.warning(
            "Wallet link signature verification failed: user_id=%d address=%s...",
            user.id,
            request.address[:10],
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="signature verification failed",
        )

    address_lower = request.address.lower()

    # 既存リンクチェック
    existing = AuthService.get_user_by_wallet(db, address_lower)
    if existing is not None and existing.id != user.id:
        # 404: 両ユーザーに privy_did が設定済みかつ不一致 → 別人扱い
        if user.privy_did and existing.privy_did and user.privy_did != existing.privy_did:
            logger.warning(
                "Wallet link DID mismatch: jwt_user=%d existing_user=%d address=%s...",
                user.id,
                existing.id,
                address_lower[:10],
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="JWT user does not match wallet user (privy_did mismatch)",
            )
        # 409: それ以外はウォレット重複
        logger.warning(
            "Wallet link conflict: jwt_user=%d existing_user=%d address=%s...",
            user.id,
            existing.id,
            address_lower[:10],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="wallet already linked to another account",
        )

    # 200: 紐付け
    user.wallet_address = address_lower
    db.commit()
    db.refresh(user)

    linked_at = (user.updated_at or datetime.now(timezone.utc)).isoformat()
    logger.info(
        "Wallet linked: user_id=%d wallet=%s...%s",
        user.id,
        address_lower[:10],
        address_lower[-4:],
    )
    return WalletLinkResponse(
        user_id=user.id,
        wallet_address=address_lower,
        linked_at=linked_at,
    )


class WalletUnlinkResponse(BaseModel):
    ok: bool
    user_id: int
    unlinked_address: str


@router.delete(
    "/wallet/{user_id}",
    response_model=WalletUnlinkResponse,
    summary="Admin: ユーザーのウォレットリンクを解除",
)
def wallet_unlink(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WalletUnlinkResponse:
    """
    Admin のみ実行可能。対象ユーザーの wallet_address を NULL にする。
    解除後は /auth/wallet/link で別アドレスを再リンク可能。

    レスポンス:
    - 200: 解除成功
    - 400: 既に wallet_address が未設定
    - 403: Admin 以外 (require_admin が返す)
    - 404: 対象ユーザーが存在しない
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    if user.wallet_address is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="wallet not linked")

    unlinked_address = user.wallet_address
    user.wallet_address = None
    db.commit()

    logger.info(
        "Wallet unlinked by admin: admin_id=%d target_user_id=%d wallet=%s...%s",
        admin.id,
        user.id,
        unlinked_address[:10],
        unlinked_address[-4:],
    )
    return WalletUnlinkResponse(ok=True, user_id=user.id, unlinked_address=unlinked_address)


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
