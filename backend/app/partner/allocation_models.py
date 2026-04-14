# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/allocation_models.py
"""
資金割り振りモデル定義。

fund_allocations テーブル: パートナーが各テスターに割り振った運用資金を管理する。

Phase 1.5 マイグレーション SQL（本番DB適用時）:
  ALTER TABLE fund_allocations
    ADD COLUMN tester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
  CREATE INDEX idx_fund_allocations_tester_user_id ON fund_allocations(tester_user_id);
  UPDATE fund_allocations fa
    SET tester_user_id = (
      SELECT u.id FROM users u WHERE u.username = fa.tester_name LIMIT 1
    )
  WHERE tester_user_id IS NULL;
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FundAllocation(Base):
    """
    資金割り振りテーブル。

    パートナーが Aave に預け入れた資金を、テスターごとに按分管理するためのレコード。
    allocated_amount_usd は Decimal 型のみ使用（float 禁止）。

    Attributes:
        id: プライマリキー
        partner_id: 割り振り元パートナーの users.id
        tester_name: テスター識別名（表示用）
        allocated_amount_usd: 割り振り金額（USD, Decimal）
        status: 'active' | 'withdrawn'
        allocated_at: 割り振り開始日時
        withdrawn_at: 引き出し完了日時（nullable）
        notes: メモ（nullable）
        created_at: レコード作成日時
        updated_at: レコード更新日時
    """

    __tablename__ = "fund_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tester_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Phase 1.5: FK to users.id (tester_name is deprecated but kept for backward compat)
    tester_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    allocated_amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=6), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<FundAllocation(id={self.id}, partner_id={self.partner_id}, "
            f"tester={self.tester_name!r}, amount={self.allocated_amount_usd}, "
            f"status={self.status!r})>"
        )
