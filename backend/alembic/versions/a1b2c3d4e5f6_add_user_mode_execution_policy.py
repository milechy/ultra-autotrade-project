"""add_user_mode_execution_policy

Revision ID: a1b2c3d4e5f6
Revises: 59919a6d4848
Create Date: 2026-03-23 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "59919a6d4848"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_mode and execution_policy columns to users table."""
    op.add_column(
        "users",
        sa.Column(
            "user_mode",
            sa.String(length=20),
            nullable=False,
            server_default="managed",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "execution_policy",
            sa.String(length=20),
            nullable=False,
            server_default="auto_execute",
        ),
    )


def downgrade() -> None:
    """Remove user_mode and execution_policy columns from users table."""
    op.drop_column("users", "execution_policy")
    op.drop_column("users", "user_mode")
