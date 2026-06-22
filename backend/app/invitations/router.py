# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/invitations/router.py
"""招待コード API ルーター。

公開（認証不要）の事前検証エンドポイントを提供する。register 画面が URL の
招待コードを送信前に検証し「有効/無効」を表示するために使う（2026-06-22 監査 G4）。

登録本体の検証は POST /auth/register 内の validate_code が担保しており、本 GET は
あくまで UX 用の事前チェック。enumeration 対策として、無効コードには valid=False のみ
返し、有効コードにのみ付随情報（保有者は既にコードを知っている）を返す。
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db

from .schemas import InvitationValidateResponse
from .service import validate_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@router.get("/{code}", response_model=InvitationValidateResponse)
def validate_invitation_code(
    code: str,
    db: Session = Depends(get_db),
) -> InvitationValidateResponse:
    """招待コードを事前検証する（認証不要）。

    有効なら valid=True と付随情報、無効/期限切れ/使用超過なら valid=False のみ返す。
    """
    invitation = validate_code(db, code)
    if invitation is None:
        return InvitationValidateResponse(valid=False)
    return InvitationValidateResponse(
        valid=True,
        type=invitation.type,
        partner_id=invitation.partner_id,
        expires_at=invitation.expires_at,
        uses_remaining=invitation.max_uses - invitation.used_count,
    )
