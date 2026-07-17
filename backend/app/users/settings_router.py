# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_router.py
"""ユーザー設定API ルーター定義。"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.constants import ExecutionPolicy
from app.auth.dependencies import get_current_user, require_active_user
from app.auth.models import AGGRESSIVE_ACK_VERSION, User, UserRole
from app.database import get_db
from app.partner import allocation_service
from app.partner.allocation_schemas import MyAllocationResponse
from app.privy.delegation_service import (
    DelegationPolicyError,
    DelegationPolicyNotEnabledError,
    is_delegation_policy_enabled,
    prepare_delegation_policy,
    resolve_delegation_chain_name,
)

from .models import (
    ACCOUNT_DELETION_STATUS_PENDING,
    DELEGATION_STATUS_ACTIVE,
    DELEGATION_STATUS_REVOKED,
    AccountDeletionRequest,
    DelegationGrant,
    get_active_grant,
)
from .settings_schemas import (
    DelegationGrantRequest,
    DelegationGrantResponse,
    DelegationPrepareResponse,
    PaymentMethodConfirmRequest,
    PaymentMethodResponse,
    SetupIntentResponse,
    UserSettingsResponse,
    UserSettingsUpdate,
)

logger = logging.getLogger(__name__)

LIFF_TERMS_VERSION = "liff-v4"

router = APIRouter(prefix="/api/user", tags=["user-settings"])


def _build_settings_response(user: User) -> UserSettingsResponse:
    """User ORM オブジェクトから UserSettingsResponse を構築する。

    terms_accepted_at → terms_agreed_at のフィールド名変換を行う。
    """
    return UserSettingsResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        notification_email=user.notification_email,
        notification_frequency=user.notification_frequency,
        max_single_trade_usd=user.max_single_trade_usd,
        max_daily_trade_usd=user.max_daily_trade_usd,
        user_mode=user.user_mode,
        execution_policy=user.execution_policy,
        line_monthly_opt_in=user.line_monthly_opt_in,
        terms_agreed_at=user.terms_accepted_at,
        terms_version=user.terms_version,
        aggressive_ack_at=user.aggressive_ack_at,
        risk_mode=user.risk_mode,
        corporate_fiscal_month=user.corporate_fiscal_month,
        role=user.role,
        wallet_address=user.wallet_address,
        smart_wallet_address=user.smart_wallet_address,
    )


@router.get("/settings", response_model=UserSettingsResponse, summary="設定取得")
def get_user_settings(
    current_user: User = Depends(require_active_user),
) -> UserSettingsResponse:
    """現在のユーザー設定を返す。terms_agreed_at（= terms_accepted_at）を含む。"""
    return _build_settings_response(current_user)


@router.put("/settings", response_model=UserSettingsResponse, summary="設定更新")
def update_user_settings(
    request: UserSettingsUpdate,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    """ユーザー設定を更新する。"""
    _USER_MODE_TO_POLICY = {
        "managed": ExecutionPolicy.AUTO_EXECUTE.value,
        "active": ExecutionPolicy.REQUIRE_APPROVAL.value,
        "pro": ExecutionPolicy.PROPOSAL_ONLY.value,
    }

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
    # user_mode は本人によるセルフサービス変更（role 制限なし）。
    # LIFF 運用モード画面でエンドユーザー（viewer）が自分の運用モードを
    # 「完全おまかせ(managed)/アクティブ(active)」で切り替えられるようにする。
    if request.user_mode is not None:
        if request.user_mode not in _USER_MODE_TO_POLICY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_mode must be one of: managed, active, pro",
            )
        # A-2 入金ゲート: 完全おまかせ (managed = AUTO 執行) への切替は最低入金額を要求する。
        # active/pro は per-trade 承認が挟まり approve 側ゲートで担保されるため対象外。
        # 判定不能 (None) は fail-open（インフラ起因で正規の切替を止めない）、確定不足のみブロック。
        if request.user_mode == "managed":
            from app.users.deposit_policy import MIN_DEPOSIT_USD  # noqa: PLC0415
            from app.users.deposit_resolver import resolve_user_deposit_usd  # noqa: PLC0415

            _deposit_usd = resolve_user_deposit_usd(db, current_user.id)
            if _deposit_usd is not None and _deposit_usd < MIN_DEPOSIT_USD:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "DEPOSIT_BELOW_MINIMUM",
                        "message": (
                            f"完全おまかせ運用の開始には最低 ${MIN_DEPOSIT_USD} の入金が必要です"
                            f"（現在: ${_deposit_usd}）。"
                        ),
                        "min_deposit_usd": str(MIN_DEPOSIT_USD),
                        "current_deposit_usd": str(_deposit_usd),
                    },
                )
        current_user.user_mode = request.user_mode
        current_user.execution_policy = _USER_MODE_TO_POLICY[request.user_mode]
    # execution_policy の直接指定は admin/partner のみ（低レベル操作のため温存）。
    if request.execution_policy is not None:
        if current_user.role not in (UserRole.ADMIN.value, UserRole.PARTNER.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="execution policy change is not allowed for this role",
            )
        if request.execution_policy not in ExecutionPolicy.values():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=("execution_policy must be one of: " + ", ".join(ExecutionPolicy.values())),
            )
        current_user.execution_policy = request.execution_policy
    if request.line_monthly_opt_in is not None:
        current_user.line_monthly_opt_in = request.line_monthly_opt_in
    if request.corporate_fiscal_month is not None:
        # スキーマ側で 1-12 を検証済み。設定すると TAX & REPORTS 法人モードが解放される。
        current_user.corporate_fiscal_month = request.corporate_fiscal_month
    if request.username is not None:
        # スキーマ側で形式検証 + 小文字化済み。本人による表示名変更（role 制限なし）。
        new_username = request.username
        if new_username != current_user.username:
            existing = (
                db.query(User)
                .filter(User.username == new_username, User.id != current_user.id)
                .first()
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="このユーザー名は既に使用されています",
                )
            current_user.username = new_username
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _build_settings_response(current_user)


@router.post("/terms-agree", summary="重要事項同意記録")
def agree_to_terms(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """重要事項への同意を記録する（LIFF オンボーディング用）。

    既に同意済みの場合はそのまま返す（冪等）。
    terms_accepted_at カラムに現在時刻を書き込み、terms_version=LIFF_TERMS_VERSION (liff-v4) を設定する。
    """
    # terms_version が現行 LIFF_TERMS_VERSION (liff-v4) の場合のみ同意済みとして扱う
    # — 旧バージョン (liff-v1/v3, 2.0 等) で同意済みのユーザーは再同意を求める
    if (
        current_user.terms_accepted_at is not None
        and current_user.terms_version == LIFF_TERMS_VERSION
    ):
        return {
            "terms_agreed_at": current_user.terms_accepted_at.isoformat(),
            "already_agreed": True,
        }

    now = datetime.now(timezone.utc)
    current_user.terms_accepted_at = now
    current_user.terms_version = LIFF_TERMS_VERSION
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    logger.info(
        "User %s agreed to LIFF terms at %s",
        current_user.email,
        now.isoformat(),
    )
    allocation_service.auto_fund_tester_if_enabled(db, current_user)
    return {
        "terms_agreed_at": now.isoformat(),
        "already_agreed": False,
    }


@router.post("/aggressive-consent", summary="aggressive ティア リスク開示 同意記録")
def agree_aggressive_disclosure(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """[Phase-D D5b] aggressive ティア(Pendle stablecoin PT)のリスク開示に同意を記録する。

    満期ロック(即時出金不可) / yoUSD 裏付け / スリッページ・薄い流動性リスク の全同意。
    ``/terms-agree`` を踏襲した auth-only・body なし・冪等な endpoint。現行
    ``AGGRESSIVE_ACK_VERSION`` で既に同意済みならそのまま返す。実際の aggressive 選択有効化は
    別途(PHASE_1 gate 緩和 / D6)で、本 endpoint は同意の記録のみ。
    """
    if (
        current_user.aggressive_ack_at is not None
        and current_user.aggressive_ack_version == AGGRESSIVE_ACK_VERSION
    ):
        return {
            "aggressive_ack_at": current_user.aggressive_ack_at.isoformat(),
            "already_agreed": True,
        }

    now = datetime.now(timezone.utc)
    current_user.aggressive_ack_at = now
    current_user.aggressive_ack_version = AGGRESSIVE_ACK_VERSION
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    logger.info(
        "User %s agreed to aggressive-tier disclosure (%s) at %s",
        current_user.email,
        AGGRESSIVE_ACK_VERSION,
        now.isoformat(),
    )
    return {
        "aggressive_ack_at": now.isoformat(),
        "already_agreed": False,
    }


@router.get(
    "/my-allocation",
    response_model=Optional[MyAllocationResponse],
    summary="自分への資金割り振り確認",
)
def get_my_allocation(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> Optional[MyAllocationResponse]:
    """テスター自身への資金割り振り情報を返す。割り振りがない場合は null。"""
    return allocation_service.get_my_allocation(db, current_user)


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
    # NOTE: require_active_user は使えない。pause で is_active=False にした後に resume を
    # 呼ぶため、require_active_user だと 403 "User is inactive" で永久に再開不能になる
    # (catch-22)。resume は「非アクティブな本人」が自分を再アクティブ化する操作なので
    # 認証のみ (get_current_user) を要求する。
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """運用を再開する（is_active=True）。"""
    current_user.is_active = True
    db.add(current_user)
    db.commit()
    return {"message": "resumed", "is_active": True}


@router.post("/delete-request", summary="アカウント削除申請")
def request_account_deletion(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """アカウント削除を申請する（APPI / 個人情報保護法対応 / 冪等）。

    削除申請を account_deletion_requests に記録する。既に pending の申請が
    あればそれを返す（二重申請を防ぐ）。実際の削除データ処理はバックオフィスで
    行うため、本エンドポイントは「申請の受付」までを担う。
    """
    existing = (
        db.query(AccountDeletionRequest)
        .filter(
            AccountDeletionRequest.user_id == current_user.id,
            AccountDeletionRequest.status == ACCOUNT_DELETION_STATUS_PENDING,
        )
        .first()
    )
    if existing is not None:
        return {
            "status": existing.status,
            "requested_at": existing.requested_at.isoformat(),
            "already_requested": True,
        }

    req = AccountDeletionRequest(user_id=current_user.id, status=ACCOUNT_DELETION_STATUS_PENDING)
    db.add(req)
    db.commit()
    db.refresh(req)
    logger.info(
        "User %s requested account deletion (req_id=%s)",
        current_user.email,
        req.id,
    )
    return {
        "status": req.status,
        "requested_at": req.requested_at.isoformat(),
        "already_requested": False,
    }


# ---------------------------------------------------------------------------
# 委譲枠 (delegation grant) — v4 完全おまかせ自動運用 Phase 0 / スライス0-C
# ユーザーが「この枠・このリスクで任せる」と1回 consent する事前枠承認。
# AUTO 執行時に有効な grant が無ければ fail-closed で拒否される（PolicyEngine Rule 8）。
# 実際の % 上限は執行直前に risk_limiter で二重クランプする。
# ---------------------------------------------------------------------------


def _require_aggressive_ack_for_pendle(user: User, allowed_protocols: list[str]) -> None:
    """Pendle を含む委譲はリスク開示同意（満期ロック / 裏付け / スリッページ）を必須にする。

    schema（`DelegationGrantRequest._validate_protocols`）は「委譲可能な集合か」しか見ないため、
    「そのユーザーが開示に同意済みか」は user を持つ router 側で確認する。これが無いと、
    委譲枠経由で `AggressiveRiskDisclosureModal` を迂回して Pendle 権限を取得できてしまう
    （`PUT /auth/risk-mode` の 412 ガードと同じ defense-in-depth を委譲経路にも敷く）。

    prepare / grant の両 leg で呼ぶ。prepare は Privy policy を実際に作る副作用があるため、
    権限が確定する grant だけでなく prepare でも先に止める。
    """
    if "pendle" not in allowed_protocols:
        return
    if user.aggressive_ack_at is None or user.aggressive_ack_version != AGGRESSIVE_ACK_VERSION:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Pendle を含む委譲にはリスク開示への同意が必要です。",
        )


@router.get(
    "/delegation",
    response_model=Optional[DelegationGrantResponse],
    summary="現在有効な委譲枠を取得",
)
def get_delegation_grant(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> Optional[DelegationGrantResponse]:
    """現在有効な委譲枠を返す。無ければ null。"""
    grant = get_active_grant(current_user.id, db)
    if grant is None:
        return None
    return DelegationGrantResponse.model_validate(grant)


@router.post(
    "/delegation/prepare",
    response_model=DelegationPrepareResponse,
    summary="委譲 policy を作成（L1・consent 前）",
)
def prepare_delegation_policy_endpoint(
    request: DelegationGrantRequest,
    current_user: User = Depends(require_active_user),
) -> DelegationPrepareResponse:
    """委譲枠から Privy policy を作成し ``policy_id`` / ``signer_id`` を返す（L1）。

    frontend は返値を ``addSessionSigners`` に渡して consent を取り、その後
    ``/delegation/grant`` に同じ識別子を返して枠を確定する。

    **dormant**: ``DELEGATION_PRIVY_POLICY_ENABLED`` + ``PRIVY_SERVER_SIGNER_ID``（L0 登録）+
    Privy creds が揃わない限り 503 を返し、Privy を一切叩かない（本番は現状 inert）。
    """
    # dormant: フラグ/L0 未設定なら wallet を見るまでもなく 503（Privy を叩かない）。
    if not is_delegation_policy_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "delegation policy preparation is not enabled "
                "(requires DELEGATION_PRIVY_POLICY_ENABLED + PRIVY_SERVER_SIGNER_ID after L0)"
            ),
        )
    # Pendle 委譲は開示同意必須（Privy policy を作る前に止める）。
    _require_aggressive_ack_for_pendle(current_user, request.allowed_protocols)
    now = datetime.now(timezone.utc)
    wallet = current_user.smart_wallet_address or current_user.wallet_address
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="委譲対象ウォレットが未設定です",
        )
    expires_at = now + timedelta(days=request.expires_in_days)
    chain_name = resolve_delegation_chain_name()
    try:
        policy_id, signer_id = prepare_delegation_policy(
            wallet_address=wallet,
            allowed_protocols=request.allowed_protocols,
            expires_at=expires_at,
            chain_name=chain_name,
        )
    except DelegationPolicyNotEnabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except DelegationPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DelegationPrepareResponse(
        privy_policy_id=policy_id,
        privy_signer_id=signer_id,
        chain_name=chain_name,
        expires_at=expires_at,
    )


@router.post(
    "/delegation/grant",
    response_model=DelegationGrantResponse,
    summary="委譲枠を作成（consent）",
)
def create_delegation_grant(
    request: DelegationGrantRequest,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> DelegationGrantResponse:
    """委譲枠を作成する。既存の有効枠は新規作成前に revoke する（常に1枠のみ有効）。

    上限 % は schema 段階でハードキャップ（単一≤10% / 日次≤30% / HF≥1.6）を検証済み。
    ``allowed_protocols`` も schema で委譲可能集合に正規化・検証済み（prepare と同一 schema）。
    委譲対象ウォレットは smart_wallet_address を優先、無ければ wallet_address。
    """
    # Pendle 委譲は開示同意必須（権限が DB に確定する直前で enforce）。
    _require_aggressive_ack_for_pendle(current_user, request.allowed_protocols)
    now = datetime.now(timezone.utc)

    # 既存の有効枠を revoke（1ユーザー1有効枠を維持）
    existing = get_active_grant(current_user.id, db)
    if existing is not None:
        existing.status = DELEGATION_STATUS_REVOKED
        existing.revoked_at = now

    wallet = current_user.smart_wallet_address or current_user.wallet_address
    grant = DelegationGrant(
        user_id=current_user.id,
        wallet_address=wallet,
        status=DELEGATION_STATUS_ACTIVE,
        max_single_trade_pct=request.max_single_trade_pct,
        max_daily_trade_pct=request.max_daily_trade_pct,
        hf_floor=request.hf_floor,
        allowed_protocols=request.allowed_protocols,
        allowed_assets=request.allowed_assets,
        consent_at=now,
        expires_at=now + timedelta(days=request.expires_in_days),
        # L3: consent(addSessionSigners) 後に frontend が渡す Privy 識別子（任意）。
        privy_policy_id=request.privy_policy_id,
        privy_signer_id=request.privy_signer_id,
    )
    db.add(grant)

    # 委譲 SCW 執行が要求する per-user Privy wallet ID。ログイン時点では未委譲で null のため
    # 取得できず、consent(addSigners) 完了後の本エンドポイント呼び出し時が唯一の確実な解決経路
    # （2026-07-16）。未指定時は _resolve_privy_wallet_id が env フォールバックに頼る旧経路のまま。
    if request.privy_wallet_id and current_user.privy_wallet_id != request.privy_wallet_id:
        current_user.privy_wallet_id = request.privy_wallet_id

    db.commit()
    db.refresh(grant)
    logger.info(
        "delegation grant created: user_id=%s, single=%s%%, daily=%s%%, expires_in=%dd",
        current_user.id,
        request.max_single_trade_pct,
        request.max_daily_trade_pct,
        request.expires_in_days,
    )
    return DelegationGrantResponse.model_validate(grant)


@router.post(
    "/delegation/revoke",
    response_model=Optional[DelegationGrantResponse],
    summary="委譲枠を取消",
)
def revoke_delegation_grant(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> Optional[DelegationGrantResponse]:
    """現在有効な委譲枠を取消する。無ければ null（冪等）。"""
    grant = get_active_grant(current_user.id, db)
    if grant is None:
        return None
    grant.status = DELEGATION_STATUS_REVOKED
    grant.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(grant)
    logger.info("delegation grant revoked: user_id=%s, grant_id=%s", current_user.id, grant.id)
    return DelegationGrantResponse.model_validate(grant)


# ---------------------------------------------------------------------------
# 月額サブスク課金 — Stripe カード登録 (F-7)
# 実課金 (StripeBillingAdapter) は backend/app/fees/billing_adapter.py 参照。
# 本セクションはユーザー本人による決済手段(カード)登録のみを扱う。
# ---------------------------------------------------------------------------


def _get_stripe_api_key() -> str:
    """STRIPE_SECRET_KEY 未設定時は 503 (billing 機能自体が未提供)。"""
    api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="billing is not configured (STRIPE_SECRET_KEY unset)",
        )
    return api_key


@router.post(
    "/billing/setup-intent",
    response_model=SetupIntentResponse,
    summary="カード登録用 SetupIntent 発行",
)
def create_billing_setup_intent(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> SetupIntentResponse:
    """Stripe Customer を取得/作成し、off-session 用 SetupIntent を発行する。

    frontend は返却された client_secret を Stripe.js の confirmSetup() に渡してカードを登録する。
    """
    import stripe  # noqa: PLC0415

    api_key = _get_stripe_api_key()

    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={"user_id": str(current_user.id)},
            api_key=api_key,
        )
        current_user.stripe_customer_id = customer.id
        db.add(current_user)
        db.commit()

    setup_intent = stripe.SetupIntent.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        usage="off_session",
        api_key=api_key,
    )
    return SetupIntentResponse(client_secret=setup_intent.client_secret)


@router.get(
    "/billing/payment-method",
    response_model=PaymentMethodResponse,
    summary="登録済みカード確認",
)
def get_billing_payment_method(
    current_user: User = Depends(require_active_user),
) -> PaymentMethodResponse:
    """登録済みカードの brand/last4 を返す（PAN 等の機微情報は含まない）。未登録なら registered=False。"""
    if not current_user.stripe_customer_id or not current_user.stripe_default_payment_method_id:
        return PaymentMethodResponse(registered=False)

    import stripe  # noqa: PLC0415

    api_key = _get_stripe_api_key()
    try:
        payment_method = stripe.PaymentMethod.retrieve(
            current_user.stripe_default_payment_method_id, api_key=api_key
        )
    except stripe.error.StripeError:
        # Stripe 側で削除済み等 — 未登録として扱う (fail-open)
        return PaymentMethodResponse(registered=False)

    card = payment_method.card
    return PaymentMethodResponse(
        registered=True,
        brand=card.brand if card else None,
        last4=card.last4 if card else None,
    )


@router.post(
    "/billing/payment-method/confirm",
    response_model=PaymentMethodResponse,
    summary="カード登録を確定",
)
def confirm_billing_payment_method(
    request: PaymentMethodConfirmRequest,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaymentMethodResponse:
    """frontend で confirmSetup() 完了後の setup_intent_id を検証し、
    payment_method を既定カードとして保存する。"""
    import stripe  # noqa: PLC0415

    api_key = _get_stripe_api_key()
    try:
        setup_intent = stripe.SetupIntent.retrieve(request.setup_intent_id, api_key=api_key)
    except stripe.error.StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid setup_intent: {exc}"
        ) from exc

    if setup_intent.status != "succeeded" or not setup_intent.payment_method:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"setup intent not succeeded (status={setup_intent.status})",
        )
    if (
        current_user.stripe_customer_id is None
        or setup_intent.customer != current_user.stripe_customer_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="setup intent does not belong to this user",
        )

    payment_method_id = (
        setup_intent.payment_method
        if isinstance(setup_intent.payment_method, str)
        else setup_intent.payment_method.id
    )
    stripe.Customer.modify(
        current_user.stripe_customer_id,
        invoice_settings={"default_payment_method": payment_method_id},
        api_key=api_key,
    )
    current_user.stripe_default_payment_method_id = payment_method_id
    db.add(current_user)
    db.commit()
    logger.info(
        "stripe payment method registered: user_id=%s pm_id=%s",
        current_user.id,
        payment_method_id,
    )

    payment_method = stripe.PaymentMethod.retrieve(payment_method_id, api_key=api_key)
    card = payment_method.card
    return PaymentMethodResponse(
        registered=True,
        brand=card.brand if card else None,
        last4=card.last4 if card else None,
    )
