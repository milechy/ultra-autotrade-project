# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/models.py
"""Fee Model v10 SQLAlchemy ORM 定義。

テーブル:
- fee_configs      : v10 設定 (tier × risk_mode の手数料率マトリクス)
- fee_transactions : 月次手数料計算結果

DDL の真実の源: backend/alembic/sql/045_fee_v10_tables.sql
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: PostgreSQL では JSONB、それ以外 (SQLite テスト等) では JSON を使う型 alias。
_JSONB_OR_JSON = JSONB().with_variant(JSON(), "sqlite")


class FeeConfigV10(Base):
    """v10 手数料設定。

    1 レコード = 1 つの設定スナップショット。``is_active=True`` かつ最新の
    ``effective_from`` を持つレコードが現行設定。
    """

    __tablename__ = "fee_configs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    config_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tier_thresholds_jpy: Mapped[list[int]] = mapped_column(_JSONB_OR_JSON, nullable=False)
    tier_fee_rates: Mapped[list[float]] = mapped_column(_JSONB_OR_JSON, nullable=False)
    tier_monthly_yield_caps: Mapped[list[float]] = mapped_column(_JSONB_OR_JSON, nullable=False)
    subscription_rates: Mapped[dict[str, Any]] = mapped_column(_JSONB_OR_JSON, nullable=False)
    expense_markup_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    expense_markup_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    affiliate_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0.30")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
        Index(
            "idx_fee_configs_active_effective",
            "is_active",
            text("effective_from DESC"),
        ),
    )

    def __repr__(self) -> str:
        return f"<FeeConfigV10(id={self.id}, name={self.config_name!r}, active={self.is_active})>"


class FeeTransaction(Base):
    """v10 月次手数料計算結果。

    1 ユーザー × 1 ヶ月 (calculation_month は月初日) で 1 レコード。
    ``finalized_at`` が NULL の間は再計算で上書き可能、NOT NULL になった後は確定。
    """

    __tablename__ = "fee_transactions"

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
    calculation_month: Mapped[date] = mapped_column(Date, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    deposit_amount_jpy: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gross_profit_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    expense_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    net_profit_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    fee_rate_applied: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    fee_amount_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    subscription_rate_applied: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    subscription_amount_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    subscription_protected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    monthly_yield_cap_applied: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    yield_excess_to_uata_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    user_takehome_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    affiliate_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    affiliate_amount_jpy: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    on_chain_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)

    # F-S6: on-chain fee transfer 追跡 (j0k1l2m3n4o5 migration)
    # ALTER TABLE fee_transactions ADD COLUMN IF NOT EXISTS transfer_status VARCHAR(16);
    # ALTER TABLE fee_transactions ADD COLUMN IF NOT EXISTS transfer_tx_hash VARCHAR(66);
    # ALTER TABLE fee_transactions ADD COLUMN IF NOT EXISTS usd_jpy_rate NUMERIC(8,2);
    transfer_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    transfer_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    usd_jpy_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "tier IN ('LOWER', 'MIDDLE', 'UPPER')",
            name="chk_fee_tx_tier",
        ),
        CheckConstraint(
            "risk_mode IN ('conservative', 'balanced', 'aggressive')",
            name="chk_fee_tx_risk_mode",
        ),
        UniqueConstraint("user_id", "calculation_month", name="uq_fee_tx_user_month"),
        Index(
            "idx_fee_tx_user_month",
            "user_id",
            text("calculation_month DESC"),
        ),
        Index(
            "idx_fee_tx_finalized",
            "finalized_at",
            postgresql_where=text("finalized_at IS NULL"),
        ),
        Index(
            "idx_fee_tx_affiliate",
            "affiliate_id",
            postgresql_where=text("affiliate_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FeeTransaction(id={self.id}, user_id={self.user_id}, "
            f"month={self.calculation_month}, tier={self.tier}, "
            f"risk_mode={self.risk_mode}, total={self.fee_amount_jpy})>"
        )
