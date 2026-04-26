"""add_privy_did_to_users

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add privy_did column to users table."""
    op.add_column(
        "users",
        sa.Column("privy_did", sa.String(length=255), nullable=True),
    )
    # NULL は unique 制約から除外されるため既存ユーザー (all NULL) との衝突なし
    op.create_index(
        "ix_users_privy_did",
        "users",
        ["privy_did"],
        unique=True,
        postgresql_where=sa.text("privy_did IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove privy_did column from users table."""
    op.drop_index("ix_users_privy_did", table_name="users")
    op.drop_column("users", "privy_did")
