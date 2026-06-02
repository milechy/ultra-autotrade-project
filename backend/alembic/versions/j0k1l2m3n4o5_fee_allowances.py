"""fee_allowances

Add fee_allowances table and on_chain_tx_hash column to fee_transactions.
fee_allowances tracks user→operator aToken EIP-2612 permit lifecycle.
on_chain_tx_hash stores the tx hash after FEE_TRANSFER_ENABLED=true transfers.

Asana: 1215272587496967 / 1215273755294098

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fee_transactions",
        sa.Column("on_chain_tx_hash", sa.String(66), nullable=True),
    )

    op.create_table(
        "fee_allowances",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_wallet_addr", sa.String(42), nullable=False),
        sa.Column("allowance_limit", sa.Numeric(18, 6), nullable=False),
        sa.Column("permit_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_hash_permit", sa.String(66), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
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
        sa.CheckConstraint(
            "status IN ('pending','submitted','confirmed','expired')",
            name="chk_fee_allowances_status",
        ),
    )
    op.create_index(
        "idx_fee_allowances_user",
        "fee_allowances",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_fee_allowances_user", table_name="fee_allowances")
    op.drop_table("fee_allowances")
    op.drop_column("fee_transactions", "on_chain_tx_hash")
