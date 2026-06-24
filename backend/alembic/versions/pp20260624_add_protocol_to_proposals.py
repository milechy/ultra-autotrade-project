# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_protocol_to_proposals

proposals テーブルに protocol カラム (VARCHAR(50), nullable) を追加する
(v4 マルチプロトコル対応 / Phase-A)。

提案元プロトコル ("aave" / "lido" / "pendle") を保持する。後方互換のため nullable=True
(既存提案・Aave 既定フローは NULL のまま動作する)。値は application 層で制御するため
CHECK 制約は設けない (models.py が唯一の真実源 / CLAUDE.md CHECK制約二重管理ルール)。

非破壊・既存テーブルへのカラム追加のみ。既存行への影響なし。

Revision ID: pp20260624
Revises: dg20260619
Create Date: 2026-06-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pp20260624"
down_revision: Union[str, Sequence[str], None] = "dg20260619"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add protocol column to proposals."""
    op.add_column("proposals", sa.Column("protocol", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Drop protocol column from proposals."""
    op.drop_column("proposals", "protocol")
