"""add_error_message_to_proposals_and_transactions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_message columns to proposals and transactions tables."""
    op.add_column(
        "proposals",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove error_message columns from proposals and transactions tables."""
    op.drop_column("transactions", "error_message")
    op.drop_column("proposals", "error_message")
