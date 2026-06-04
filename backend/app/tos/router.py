# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/tos/router.py
"""ToS 同意 API エンドポイント (MVP-P0-14 / GID 1215082217739006)。

POST /api/v1/tos/consent       - 同意ログ作成 (active consent)
GET  /api/v1/tos/consent/current - 最新同意の取得
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db
from app.tos.schemas import (
    ToSConsentCurrentResponse,
    ToSConsentRequest,
    ToSConsentResponse,
)
from app.tos.service import get_latest_consent, record_consent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tos", tags=["tos-consent"])

_MAX_UA_LEN = 512
_MAX_IP_LEN = 64


def _client_ip(request: Request) -> str | None:
    """X-Forwarded-For を尊重しつつ client IP を抽出する (proxy chain 対応)。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first[:_MAX_IP_LEN]
    if request.client and request.client.host:
        return request.client.host[:_MAX_IP_LEN]
    return None


@router.post(
    "/consent",
    response_model=ToSConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ToS active consent ログを記録する",
)
def create_consent(
    payload: ToSConsentRequest,
    request: Request,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ToSConsentResponse:
    """ToS 同意ログを永続化する。

    要件:
        - is_demo_ack = True 必須 (デモ運用 / 実資金は動かさない明示同意)
        - fully_read = True 必須 (UI 側スクロール追跡で全文読了したことの宣言)

    どちらかが False の場合、422 を返して永続化を拒否する。
    """
    if not payload.fully_read:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ToS 全文を読了してから同意してください",
        )
    if not payload.is_demo_ack:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="デモ運用 (実資金は動かない) への明示同意が必要です",
        )

    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    if user_agent is not None:
        user_agent = user_agent[:_MAX_UA_LEN]

    consent = record_consent(
        db,
        user_id=user.id,
        tos_version=payload.tos_version,
        ip=ip,
        user_agent=user_agent,
        is_demo_ack=payload.is_demo_ack,
    )
    return ToSConsentResponse.model_validate(consent)


@router.get(
    "/consent/current",
    response_model=ToSConsentCurrentResponse,
    summary="現在ログイン中ユーザーの最新 ToS 同意を返す",
)
def get_current_consent(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ToSConsentCurrentResponse:
    """最新の同意レコードを返す。未同意なら has_consent=False。"""
    latest = get_latest_consent(db, user.id)
    if latest is None:
        return ToSConsentCurrentResponse(has_consent=False, latest=None)
    return ToSConsentCurrentResponse(
        has_consent=True,
        latest=ToSConsentResponse.model_validate(latest),
    )
