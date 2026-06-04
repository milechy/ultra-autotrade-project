# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""proposals_fee_rate_server_default

proposals.fee_rate / proposals.fee_amount に server_default='0' を追加する (Lane 5)。

背景:
  2026-06-04 本番 proposal id=16 (山本さん非管理型 supply) で fee_rate/fee_amount が NULL。
  non-custodial submit-tx 経路では fee_model_v10 が proposal に記録されていなかった。
  本 migration でカラムに server_default を付与し、アプリ側の配線漏れを DB レベルでも防ぐ。

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-06-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, Sequence[str], None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """proposals.fee_rate / fee_amount に server_default='0' を付与する。"""
    op.alter_column(
        "proposals",
        "fee_rate",
        server_default=sa.text("0"),
        existing_type=sa.Numeric(precision=10, scale=6),
        existing_nullable=True,
    )
    op.alter_column(
        "proposals",
        "fee_amount",
        server_default=sa.text("0"),
        existing_type=sa.Numeric(precision=20, scale=2),
        existing_nullable=True,
    )


def downgrade() -> None:
    """server_default を削除して元の状態に戻す。"""
    op.alter_column(
        "proposals",
        "fee_amount",
        server_default=None,
        existing_type=sa.Numeric(precision=20, scale=2),
        existing_nullable=True,
    )
    op.alter_column(
        "proposals",
        "fee_rate",
        server_default=None,
        existing_type=sa.Numeric(precision=10, scale=6),
        existing_nullable=True,
    )
