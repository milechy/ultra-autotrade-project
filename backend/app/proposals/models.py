# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/models.py
"""提案モデル定義。"""
#
# DB マイグレーション:
#   fee_rate / fee_amount / error_message: c3d4e5f6a7b8 / d4e5f6a7b8c9 ほかで alembic 化済み。
#   execution_attempts: h8i9j0k1l2m3_add_proposals_execution_attempts.py で alembic 化
#                       (launch_gate L0 schema sync, 2026-05-27)。
#                       適用前は本ファイル先頭のコメント記載通り手動 ALTER で先行投入されていた。
#   expected_from / expected_to: non-custodial method2 submit-tx on-chain receipt 検証用 (2026-06-01)。
#   ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_from VARCHAR(42);
#   ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_to VARCHAR(42);
#   expiry_reminder_sent_at: j0k1l2m3n4o5_add_proposals_expiry_reminder_sent.py で alembic 化 (2026-06-03).
#   ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expiry_reminder_sent_at TIMESTAMPTZ;

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Proposal(Base):
    """提案テーブル。"""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ai_decision_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=36, scale=18), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_hf_after: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    estimated_gas_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    fee_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # execution_attempts: Aave 実行試行回数 (2026-05-21 P0 デッドレター化対策)
    # MAX_EXECUTION_ATTEMPTS (= 3) 超過で status を 'failed' に強制遷移させ再試行を停止する。
    # server_default='0' は alembic h8i9j0k1l2m3 migration (launch_gate L0 schema sync) と同期。
    execution_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # submit-tx receipt 検証: partner が送信した tx の from/to アドレスを保存して照合する
    expected_from: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    expected_to: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiry_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
