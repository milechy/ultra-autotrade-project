"""add_proposals_execution_attempts

Add execution_attempts column to proposals table for retry counting and
dead-letter (P0: Stream 2 retry runaway prevention, 2026-05-21).

Background:
- backend/app/proposals/models.py には既に execution_attempts: Integer (default=0)
  が定義されており、staging/production DB には手動 ALTER で先行投入済み。
- launch_gate L0 (schema sync) で「コード ↔ alembic ↔ DB」の三者一致を担保するため、
  本マイグレーションで alembic 履歴に正式登録する。

このマイグレーションは g7h8i9j0k1l2 を親とする通常 revision で、
proposals.execution_attempts を冪等に追加する。

Idempotent:
- postgres: ADD COLUMN IF NOT EXISTS を使い、既に手動 ALTER 済みの DB でも no-op。
- sqlite (テスト): batch_alter_table で対応。テスト DB には未投入なので新規追加。

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-05-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add execution_attempts column to proposals table (idempotent)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 本番/staging には手動 ALTER で先行投入済み。IF NOT EXISTS で冪等に。
        op.execute(
            "ALTER TABLE proposals "
            "ADD COLUMN IF NOT EXISTS execution_attempts INTEGER NOT NULL DEFAULT 0"
        )
    else:
        # SQLite (テスト用 fallback)
        op.add_column(
            "proposals",
            sa.Column(
                "execution_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Remove execution_attempts column from proposals table."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE proposals DROP COLUMN IF EXISTS execution_attempts")
    else:
        with op.batch_alter_table("proposals") as batch_op:
            batch_op.drop_column("execution_attempts")
