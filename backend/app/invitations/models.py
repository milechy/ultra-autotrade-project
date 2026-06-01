# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/invitations/models.py
"""
招待コードモデル定義。

Migration (ALTER TABLE):
  -- j0k1l2m3n4o5: open registration mode 対応
  ALTER TABLE invitations ADD COLUMN type VARCHAR(10) NOT NULL DEFAULT 'invite';
  ALTER TABLE invitations ALTER COLUMN partner_id DROP NOT NULL;
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

INVITATION_TYPE_OPEN = "open"
INVITATION_TYPE_INVITE = "invite"


class Invitation(Base):
    """
    招待コードテーブル。

    Attributes:
        id:              プライマリキー
        code:            招待コード（16文字ランダム、ユニーク）
        type:            招待種別 (open | invite)。open は partner 認証不要。
        partner_id:      発行者ユーザーID（FK: users.id）。open 登録時は NULL。
        expires_at:      有効期限
        max_uses:        最大使用回数（デフォルト1）
        used_count:      使用済み回数
        created_at:      作成日時
        invited_user_id: 招待経由で登録したユーザーID（max_uses=1の場合に設定）
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(10), nullable=False, default=INVITATION_TYPE_INVITE, server_default=INVITATION_TYPE_INVITE
    )
    partner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    invited_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<Invitation(id={self.id}, code={self.code}, type={self.type}, partner_id={self.partner_id})>"
