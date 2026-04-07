# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/invitations/router.py
"""
招待コード API エンドポイント。

POST /api/invitations       — 招待コード発行（partner/admin のみ）
GET  /api/invitations       — 自分の招待コード一覧（partner/admin のみ）
GET  /api/invitations/{code} — コード検証（認証不要）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

from . import service
from .schemas import InvitationCreateRequest, InvitationResponse, InvitationValidateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

_PARTNER_ROLES = ("partner", "admin")


async def require_partner(user: User = Depends(require_active_user)) -> User:
    """
    partner または admin ロールを要求する。

    Note: Wave 1 で auth/dependencies.py に追加予定。
    それまでの間はここで定義する。
    """
    if user.role not in _PARTNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner or admin access required",
        )
    return user


@router.post(
    "",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="招待コード発行",
)
def create_invitation(
    request: InvitationCreateRequest,
    user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """招待コードを発行する。partner/admin のみ実行可能。"""
    invitation = service.create_invitation(
        db,
        partner_id=user.id,
        expires_at=request.expires_at,
        max_uses=request.max_uses,
    )
    logger.info("Invitation created by user_id=%d", user.id)
    return InvitationResponse.model_validate(invitation)


@router.get(
    "",
    response_model=list[InvitationResponse],
    summary="自分の招待コード一覧",
)
def list_invitations(
    user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> list[InvitationResponse]:
    """自分が発行した招待コードの一覧を返す。"""
    invitations = service.get_partner_invitations(db, partner_id=user.id)
    return [InvitationResponse.model_validate(i) for i in invitations]


@router.get(
    "/{code}",
    response_model=InvitationValidateResponse,
    summary="招待コード検証",
)
def validate_invitation(
    code: str,
    db: Session = Depends(get_db),
) -> InvitationValidateResponse:
    """招待コードの有効性を検証する（認証不要）。"""
    invitation = service.validate_code(db, code)
    if invitation is None:
        return InvitationValidateResponse(valid=False)
    return InvitationValidateResponse(
        valid=True,
        partner_id=invitation.partner_id,
        expires_at=invitation.expires_at,
        uses_remaining=invitation.max_uses - invitation.used_count,
    )
