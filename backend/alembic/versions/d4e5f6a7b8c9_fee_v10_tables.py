"""fee_v10_tables

Drop v9 billing tables (fee_configs / fee_calculations / high_water_marks)
and create v10 fee model tables (fee_configs / fee_transactions).

Equivalent raw SQL: backend/alembic/sql/045_fee_v10_tables.sql

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-25 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop v9 billing tables, create v10 fee_configs / fee_transactions."""
    op.drop_table("fee_calculations")
    op.drop_table("high_water_marks")
    op.drop_table("fee_configs")

    op.create_table(
        "fee_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("config_name", sa.String(64), nullable=False, unique=True),
        sa.Column("tier_thresholds_jpy", postgresql.JSONB(), nullable=False),
        sa.Column("tier_fee_rates", postgresql.JSONB(), nullable=False),
        sa.Column("tier_monthly_yield_caps", postgresql.JSONB(), nullable=False),
        sa.Column("subscription_rates", postgresql.JSONB(), nullable=False),
        sa.Column(
            "expense_markup_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "expense_markup_rate",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "affiliate_rate",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("0.30"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_fee_configs_active_effective",
        "fee_configs",
        ["is_active", sa.text("effective_from DESC")],
    )

    op.create_table(
        "fee_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calculation_month", sa.Date(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("risk_mode", sa.String(16), nullable=False),
        sa.Column("deposit_amount_jpy", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "gross_profit_jpy", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("expense_jpy", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("net_profit_jpy", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "fee_rate_applied", sa.Numeric(6, 4), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("fee_amount_jpy", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "subscription_rate_applied",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "subscription_amount_jpy",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "subscription_protected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "monthly_yield_cap_applied",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "yield_excess_to_uata_jpy",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "user_takehome_jpy",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "affiliate_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "affiliate_amount_jpy",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("tier IN ('LOWER', 'MIDDLE', 'UPPER')", name="chk_fee_tx_tier"),
        sa.CheckConstraint("risk_mode IN ('LOW', 'MIDDLE', 'HIGH')", name="chk_fee_tx_risk_mode"),
        sa.UniqueConstraint("user_id", "calculation_month", name="uq_fee_tx_user_month"),
    )
    op.create_index(
        "idx_fee_tx_user_month",
        "fee_transactions",
        ["user_id", sa.text("calculation_month DESC")],
    )
    op.create_index(
        "idx_fee_tx_finalized",
        "fee_transactions",
        ["finalized_at"],
        postgresql_where=sa.text("finalized_at IS NULL"),
    )
    op.create_index(
        "idx_fee_tx_affiliate",
        "fee_transactions",
        ["affiliate_id"],
        postgresql_where=sa.text("affiliate_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Restore v9 billing tables and drop v10 tables.

    Note: v9 schema is reconstructed from backend/app/billing/models.py.
    Existing data (if any) is NOT restored.
    """
    op.drop_index("idx_fee_tx_affiliate", table_name="fee_transactions")
    op.drop_index("idx_fee_tx_finalized", table_name="fee_transactions")
    op.drop_index("idx_fee_tx_user_month", table_name="fee_transactions")
    op.drop_table("fee_transactions")

    op.drop_index("idx_fee_configs_active_effective", table_name="fee_configs")
    op.drop_table("fee_configs")

    op.create_table(
        "fee_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "management_fee_rate",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0.005"),
        ),
        sa.Column(
            "performance_fee_rate",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0.10"),
        ),
        sa.Column(
            "high_water_mark_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "minimum_aum",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("3000"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_table(
        "high_water_marks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("hwm_value", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_high_water_marks_user_id", "high_water_marks", ["user_id"])

    op.create_table(
        "fee_calculations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False),
        sa.Column("aum_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("management_fee", sa.Numeric(18, 6), nullable=False),
        sa.Column("performance_fee", sa.Numeric(18, 6), nullable=False),
        sa.Column("total_fee", sa.Numeric(18, 6), nullable=False),
        sa.Column("profit_since_hwm", sa.Numeric(18, 6), nullable=False),
        sa.Column("high_water_mark", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_fee_calculations_user_id", "fee_calculations", ["user_id"])
