"""add delivered column to notification_logs

「送信した」(行の存在) と「到達した」(この列) を区別するための列追加 (PR3、
実行パイプライン復旧 GID 1217143339626810)。NULL=対象外/未計測。実際の書き込み配線は
別PR(PR5)で行う。

Revision ID: y6z7a8b9c0d1
Revises: x4y5z6a7b8c9
Create Date: 2026-08-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "y6z7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("delivered", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_logs", "delivered")
