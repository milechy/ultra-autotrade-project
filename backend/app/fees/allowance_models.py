# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/allowance_models.py
"""FeeAllowance ORM モデル。

fee_allowances テーブル: user→operator aToken EIP-2612 permit 追跡。
DDL: backend/alembic/sql/050_fee_allowances.sql
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeeAllowance(Base):
    """user→operator aToken EIP-2612 permit 追跡レコード。

    status lifecycle: pending → submitted → confirmed | expired
    - pending: permit typed data を生成したがまだ on-chain submit していない
    - submitted: permit tx を送信済み (mempool)
    - confirmed: permit が block に含まれた (allowance set 確認済み)
    - expired: permit_deadline が過ぎた / tx がリバートした
    """

    __tablename__ = "fee_allowances"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_wallet_addr: Mapped[str] = mapped_column(String(42), nullable=False)
    allowance_limit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    permit_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tx_hash_permit: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','submitted','confirmed','expired')",
            name="chk_fee_allowances_status",
        ),
        Index("idx_fee_allowances_user", "user_id", text("created_at DESC")),
    )

    def __repr__(self) -> str:
        return (
            f"<FeeAllowance(id={self.id}, user_id={self.user_id}, "
            f"status={self.status!r}, limit={self.allowance_limit})>"
        )
