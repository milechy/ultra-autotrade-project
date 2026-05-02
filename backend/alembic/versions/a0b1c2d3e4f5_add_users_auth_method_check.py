"""add_users_auth_method_check

GID 1214176336328111: users_auth_method_check CHECK 制約追加 + hashed_password nullable 化。
Privy-only ユーザー対応の前準備として、hashed_password を NULL 許容にしたうえで
「hashed_password IS NOT NULL OR privy_did IS NOT NULL」CHECK 制約を追加する。

Revision ID: a0b1c2d3e4f5
Revises: f6a7b8c9d0e1
Create Date: 2026-05-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make hashed_password nullable and add auth method check constraint."""
    # hashed_password を nullable 化 (Privy-only ユーザーをサポートするため)
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=True,
        )
    # CHECK 制約追加: 少なくとも一方の認証手段を必須化
    op.create_check_constraint(
        "users_auth_method_check",
        "users",
        "hashed_password IS NOT NULL OR privy_did IS NOT NULL",
    )


def downgrade() -> None:
    """Remove auth method check constraint and restore hashed_password NOT NULL."""
    op.drop_constraint("users_auth_method_check", "users", type_="check")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=False,
        )
