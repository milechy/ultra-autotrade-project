"""tos_consents and tos_user_actions tables (MVP-P0-14)

ToS 同意ログ (改ざん検知 hash 付き) と Hermes 学習データ用ユーザー行動ログを追加。
GID 1215082217739006

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, Sequence[str], None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tos_consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tos_version", sa.String(length=32), nullable=False),
        sa.Column(
            "consent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("consent_hash", sa.String(length=64), nullable=False),
        sa.Column("is_demo_ack", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tos_consents_user_id", "tos_consents", ["user_id"])
    op.create_index("ix_tos_consents_consent_at", "tos_consents", [sa.text("consent_at DESC")])

    op.create_table(
        "tos_user_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tos_user_actions_user_id", "tos_user_actions", ["user_id"])
    op.create_index("ix_tos_user_actions_action_type", "tos_user_actions", ["action_type"])
    op.create_index(
        "ix_tos_user_actions_created_at", "tos_user_actions", [sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("tos_user_actions")
    op.drop_table("tos_consents")
