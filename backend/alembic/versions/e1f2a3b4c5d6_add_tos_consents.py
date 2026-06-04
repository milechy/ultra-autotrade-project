# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_tos_consents

P0-14 (ToS active consent UI + 同意ログ永続化) の DB schema。

Revision ID: e1f2a3b4c5d6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-25 00:00:00.000000

注: alembic heads が a7b8c9d0e1f2 と g7h8i9j0k1l2 の 2 つに分岐している。
本 migration は a7b8c9d0e1f2 のみを親とする。g7 との合流は別 PR で
merge migration を作成する想定 (本 PR の責務外)。
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tos_consents table."""
    op.create_table(
        "tos_consents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tos_version", sa.String(length=32), nullable=False),
        sa.Column("consent_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "consented_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("ua", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "tos_version", name="uq_tos_consents_user_version"),
    )
    op.create_index(
        "ix_tos_consents_user_id",
        "tos_consents",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_tos_consents_user_version",
        "tos_consents",
        ["user_id", "tos_version"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tos_consents table."""
    op.drop_index("ix_tos_consents_user_version", table_name="tos_consents")
    op.drop_index("ix_tos_consents_user_id", table_name="tos_consents")
    op.drop_table("tos_consents")
