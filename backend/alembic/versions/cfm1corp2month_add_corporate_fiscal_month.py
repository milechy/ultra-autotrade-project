# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_corporate_fiscal_month

users テーブルに corporate_fiscal_month カラムを追加する (corporate-CSV [2/4])。

法人決算月 (1-12) を保持し、TAX & REPORTS の法人モード (freee/弥生 CSV)
アンロック条件に用いる。NULL = 個人ユーザー (法人モード未設定)。

Revision ID: cfm1corp2month
Revises: u1v2w3x4y5z6
Create Date: 2026-06-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfm1corp2month"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "corporate_fiscal_month",
            sa.SmallInteger(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "corporate_fiscal_month")
