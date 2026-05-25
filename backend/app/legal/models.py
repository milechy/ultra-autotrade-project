# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/legal/models.py
"""ToS consent log の SQLAlchemy model (P0-14)。

設計:
- 1 ユーザ × 1 ToS version で 1 行 (unique constraint)。
- ``consent_hash`` は同意時の ToS 全文の SHA-256 (改ざん検知 + 完全一致確認)。
- ``ip`` / ``ua`` は legal audit 時に有用。null 可 (IP マスキング等の運用裁量)。
- ``withdrawn_at`` が non-null なら同意撤回。撤回後は新規取引を停止する想定 (UI/policy 別レイヤ)。

依存:
- ``app.database.Base``
- 既存 ``users`` テーブル (FK)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TosConsent(Base):
    """ToS 同意ログ。

    Attributes:
        id: 主キー (auto increment)。
        user_id: ``users.id`` への FK。
        tos_version: 同意時の ToS バージョン文字列 (例 ``"2026-05-25"``)。
        consent_hash: ToS 全文の SHA-256 hex (64 文字)。
        consented_at: 同意時刻 (timezone aware)。
        ip: クライアント IP (最大 45 文字、IPv6 対応)。
        ua: User-Agent 文字列 (Text、長くなり得るため)。
        withdrawn_at: 撤回時刻 (null = 撤回されていない)。
    """

    __tablename__ = "tos_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tos_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    ua: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "tos_version", name="uq_tos_consents_user_version"),
        Index("ix_tos_consents_user_version", "user_id", "tos_version"),
    )

    def __repr__(self) -> str:
        return (
            f"<TosConsent id={self.id} user_id={self.user_id} "
            f"tos_version={self.tos_version!r} withdrawn={self.withdrawn_at is not None}>"
        )
