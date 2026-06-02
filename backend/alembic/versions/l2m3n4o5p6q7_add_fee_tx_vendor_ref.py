"""add_fee_tx_vendor_ref

Add vendor_reference_id and charged_at columns to fee_transactions.
Enables vendor-agnostic billing adapter result persistence (F-7).

Equivalent raw SQL: backend/alembic/sql/047_fee_tx_vendor_ref.sql

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vendor_reference_id and charged_at to fee_transactions."""
    op.add_column(
        "fee_transactions",
        sa.Column("vendor_reference_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "fee_transactions",
        sa.Column("charged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_fee_tx_vendor_ref",
        "fee_transactions",
        ["vendor_reference_id"],
        postgresql_where=sa.text("vendor_reference_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove vendor_reference_id and charged_at from fee_transactions."""
    op.drop_index("idx_fee_tx_vendor_ref", table_name="fee_transactions")
    op.drop_column("fee_transactions", "charged_at")
    op.drop_column("fee_transactions", "vendor_reference_id")
