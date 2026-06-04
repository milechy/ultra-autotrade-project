"""add_proposals_execution_route

Add execution route branching columns to proposals (P0-2, 2026-06-03):
- execution_route (NOT NULL, default 'onchain_aave'): CEX 本線 / on-chain Aave opt-in
- cex_order_id / cex_response: CEX 経路の執行証跡 (order_id = tx_id, 生レスポンス)
- CHECK 制約 ck_proposals_execution_route: ExecutionRoute.values() を文字通り使用

背景 (Asana 1215364069502631):
- proposal ごとに執行経路を作成時に確定し immutable 保持する。経路と執行証跡の
  食い違い (誤執行) を構造的に防ぐ。

CHECK 制約 enum は app.proposals.execution_route.ExecutionRoute を唯一の真実源とし、
本 migration は import して値を文字通り埋め込む (CLAUDE.md「CHECK制約と migration の
二重管理ルール」遵守 / 独自 enum 定義禁止)。

Idempotent:
- postgresql: ADD COLUMN IF NOT EXISTS。CHECK 制約は存在確認後に追加。
- sqlite (テスト): batch_alter_table。CHECK は models.py の __table_args__ が
  create_all 時に付与するため、本 migration では列追加のみ。

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-06-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.proposals.execution_route import DEFAULT_EXECUTION_ROUTE, ExecutionRoute

# revision identifiers, used by Alembic.
revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, Sequence[str], None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CHECK_NAME = "ck_proposals_execution_route"
_CHECK_SQL = "execution_route IN (" + ", ".join(f"'{v}'" for v in ExecutionRoute.values()) + ")"


def upgrade() -> None:
    """Add execution_route / cex_order_id / cex_response columns (idempotent)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS execution_route "
            f"VARCHAR(20) NOT NULL DEFAULT '{DEFAULT_EXECUTION_ROUTE}'"
        )
        op.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS cex_order_id VARCHAR(100)")
        op.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS cex_response TEXT")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_proposals_execution_route ON proposals (execution_route)"
        )
        # CHECK 制約は IF NOT EXISTS が無いので存在確認してから追加する。
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{_CHECK_NAME}'
                ) THEN
                    ALTER TABLE proposals ADD CONSTRAINT {_CHECK_NAME}
                        CHECK ({_CHECK_SQL});
                END IF;
            END $$;
            """
        )
    else:
        # SQLite (テスト fallback): 列追加のみ。CHECK は models.py __table_args__ が付与。
        with op.batch_alter_table("proposals") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "execution_route",
                    sa.String(length=20),
                    nullable=False,
                    server_default=DEFAULT_EXECUTION_ROUTE,
                )
            )
            batch_op.add_column(sa.Column("cex_order_id", sa.String(length=100), nullable=True))
            batch_op.add_column(sa.Column("cex_response", sa.Text(), nullable=True))
        op.create_index("ix_proposals_execution_route", "proposals", ["execution_route"])


def downgrade() -> None:
    """Remove execution route columns from proposals table."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE proposals DROP CONSTRAINT IF EXISTS {_CHECK_NAME}")
        op.execute("DROP INDEX IF EXISTS ix_proposals_execution_route")
        op.execute("ALTER TABLE proposals DROP COLUMN IF EXISTS cex_response")
        op.execute("ALTER TABLE proposals DROP COLUMN IF EXISTS cex_order_id")
        op.execute("ALTER TABLE proposals DROP COLUMN IF EXISTS execution_route")
    else:
        op.drop_index("ix_proposals_execution_route", table_name="proposals")
        with op.batch_alter_table("proposals") as batch_op:
            batch_op.drop_column("cex_response")
            batch_op.drop_column("cex_order_id")
            batch_op.drop_column("execution_route")
