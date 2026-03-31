"""add_wallet_address

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add wallet_address column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "wallet_address",
            sa.String(length=42),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_users_wallet_address", "users", ["wallet_address"])
    op.create_index("ix_users_wallet_address", "users", ["wallet_address"], unique=True)


def downgrade() -> None:
    """Remove wallet_address column from users table."""
    op.drop_index("ix_users_wallet_address", table_name="users")
    op.drop_constraint("uq_users_wallet_address", "users", type_="unique")
    op.drop_column("users", "wallet_address")
