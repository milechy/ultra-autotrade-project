# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_router.py
"""ユーザー設定API ルーター定義。"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.constants import ExecutionPolicy
from app.auth.dependencies import require_active_user
from app.auth.models import User, UserRole
from app.database import get_db
from app.partner import allocation_service
from app.partner.allocation_schemas import MyAllocationResponse

from .models import ACCOUNT_DELETION_STATUS_PENDING, AccountDeletionRequest
from .settings_schemas import UserSettingsResponse, UserSettingsUpdate

logger = logging.getLogger(__name__)

LIFF_TERMS_VERSION = "liff-v3"

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
        corporate_fiscal_month=user.corporate_fiscal_month,
        role=user.role,
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
    terms_accepted_at カラムに現在時刻を書き込み、terms_version="liff-v3" を設定する。
    """
    # terms_version が liff-v3 の場合のみ同意済みとして扱う
    # — 旧バージョン (liff-v1, 2.0 等) で同意済みのユーザーは再同意を求める
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
    return {
        "terms_agreed_at": now.isoformat(),
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
    current_user: User = Depends(require_active_user),
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
