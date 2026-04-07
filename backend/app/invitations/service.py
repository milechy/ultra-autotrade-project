# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/invitations/service.py
"""
招待コードサービス。

コード生成・検証・使用回数管理を担当。
"""

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import Invitation

logger = logging.getLogger(__name__)

_CODE_LENGTH = 16
_CODE_ALPHABET = string.ascii_letters + string.digits


def _generate_unique_code(db: Session) -> str:
    """重複しない16文字のランダムコードを生成する。"""
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if not db.query(Invitation).filter(Invitation.code == code).first():
            return code
    raise RuntimeError("Failed to generate unique invitation code after 10 attempts")


def create_invitation(
    db: Session,
    partner_id: int,
    expires_at: datetime,
    max_uses: int = 1,
) -> Invitation:
    """
    招待コードを作成する。

    Args:
        db:         データベースセッション
        partner_id: 発行者ユーザーID
        expires_at: 有効期限
        max_uses:   最大使用回数

    Returns:
        作成された Invitation
    """
    code = _generate_unique_code(db)
    invitation = Invitation(
        code=code,
        partner_id=partner_id,
        expires_at=expires_at,
        max_uses=max_uses,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    logger.info("Created invitation: code=%s partner_id=%d", code, partner_id)
    return invitation


def validate_code(db: Session, code: str) -> Optional[Invitation]:
    """
    招待コードを検証する。

    有効条件:
    - コードが存在する
    - 有効期限内
    - 使用回数が max_uses 未満

    Args:
        db:   データベースセッション
        code: 招待コード

    Returns:
        有効な Invitation、または None（無効/期限切れ/使用超過）
    """
    invitation = db.query(Invitation).filter(Invitation.code == code).first()
    if invitation is None:
        return None
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    if invitation.used_count >= invitation.max_uses:
        return None
    return invitation


def increment_usage(
    db: Session,
    invitation: Invitation,
    user_id: Optional[int] = None,
) -> Invitation:
    """
    招待コードの使用回数を +1 する。

    max_uses == 1 の場合は invited_user_id も設定する。

    Args:
        db:         データベースセッション
        invitation: 対象 Invitation
        user_id:    招待経由で登録したユーザーID（任意）

    Returns:
        更新された Invitation
    """
    invitation.used_count += 1
    if user_id is not None and invitation.max_uses == 1:
        invitation.invited_user_id = user_id
    db.commit()
    db.refresh(invitation)
    return invitation


def get_partner_invitations(db: Session, partner_id: int) -> list[Invitation]:
    """
    パートナーが発行した招待コード一覧を取得する。

    Args:
        db:         データベースセッション
        partner_id: パートナーユーザーID

    Returns:
        Invitation のリスト（作成日時降順）
    """
    return (
        db.query(Invitation)
        .filter(Invitation.partner_id == partner_id)
        .order_by(Invitation.created_at.desc())
        .all()
    )
