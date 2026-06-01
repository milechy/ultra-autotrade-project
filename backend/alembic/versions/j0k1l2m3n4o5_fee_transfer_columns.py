"""add_fee_transfer_columns

fee_transactions テーブルに on-chain 送金追跡カラムを追加する (F-S6)。

Columns added:
  transfer_status   VARCHAR(16)  NULL: 'sent'|'failed'|'no_allowance'|'low_fee'|'skipped'
  transfer_tx_hash  VARCHAR(66)  NULL: on-chain tx hash (0x... 64 hex)
  usd_jpy_rate      NUMERIC(8,2) NULL: 計算時の USD/JPY レート (手数料 USD 換算に使用)

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-06-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """fee_transactions に on-chain 送金追跡カラムを追加。"""
    op.add_column(
        "fee_transactions",
        sa.Column("transfer_status", sa.String(16), nullable=True),
    )
    op.add_column(
        "fee_transactions",
        sa.Column("transfer_tx_hash", sa.String(66), nullable=True),
    )
    op.add_column(
        "fee_transactions",
        sa.Column("usd_jpy_rate", sa.Numeric(8, 2), nullable=True),
    )
    op.create_index(
        "idx_fee_tx_transfer_status",
        "fee_transactions",
        ["transfer_status"],
        postgresql_where=sa.text("transfer_status IS NOT NULL"),
    )


def downgrade() -> None:
    """追加したカラムとインデックスを削除。"""
    op.drop_index("idx_fee_tx_transfer_status", table_name="fee_transactions")
    op.drop_column("fee_transactions", "usd_jpy_rate")
    op.drop_column("fee_transactions", "transfer_tx_hash")
    op.drop_column("fee_transactions", "transfer_status")
