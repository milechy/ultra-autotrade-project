"""add_proposals_expiry_reminder_sent

expire 前再通知 rail (MVP-P0-10 延長): proposals.expiry_reminder_sent_at カラムを追加。
pending な proposal が expires_at の N 分前に通知済みかを追跡し、重複通知を防ぐ。

Revision ID: 6a2621bd89
Revises: n4o5p6q7r8s9
Create Date: 2026-06-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6a2621bd89"
down_revision: Union[str, Sequence[str], None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add expiry_reminder_sent_at column to proposals table (idempotent)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expiry_reminder_sent_at TIMESTAMPTZ"
        )
    else:
        op.add_column(
            "proposals",
            sa.Column(
                "expiry_reminder_sent_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Remove expiry_reminder_sent_at column from proposals table."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE proposals DROP COLUMN IF EXISTS expiry_reminder_sent_at")
    else:
        with op.batch_alter_table("proposals") as batch_op:
            batch_op.drop_column("expiry_reminder_sent_at")
