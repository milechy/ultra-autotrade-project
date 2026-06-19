# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_delegation_grants

delegation_grants テーブルを追加する（v4 完全おまかせ自動運用 Phase 0 / スライス0-C）。

事前枠承認（委譲枠）を耐久記録する新規テーブル。ユーザーが「この枠・このリスクで任せる」と
1回 consent した内容を保持し、AUTO 執行時に有効な grant が無ければ fail-closed で拒否する
真実源になる。上限は % で保持し、実行時に risk_limiter ハード上限へ二重クランプする。

status は application-layer で制御（active / revoked / expired）。models.py を唯一の真実源とし、
CHECK 制約を本 migration 内で独自定義しない（CLAUDE.md CHECK制約二重管理ルール）。

非破壊・新規テーブル追加のみ。既存テーブルへの影響なし。

Revision ID: dg20260619
Revises: swa20260618
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dg20260619"
down_revision: Union[str, Sequence[str], None] = "swa20260618"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create delegation_grants table."""
    op.create_table(
        "delegation_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wallet_address", sa.String(length=42), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("max_single_trade_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_daily_trade_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("hf_floor", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("allowed_protocols", sa.JSON(), nullable=False),
        sa.Column("allowed_assets", sa.JSON(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("privy_policy_id", sa.String(length=255), nullable=True),
        sa.Column("privy_signer_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_delegation_grants_user_id", "delegation_grants", ["user_id"])


def downgrade() -> None:
    """Drop delegation_grants table."""
    op.drop_index("ix_delegation_grants_user_id", table_name="delegation_grants")
    op.drop_table("delegation_grants")
