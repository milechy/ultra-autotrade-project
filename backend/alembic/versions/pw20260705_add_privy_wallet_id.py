# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_privy_wallet_id

users に privy_wallet_id (Privy 内部 wallet ID・アドレスではない) を追加する。
委譲(SCW)執行の Privy wallet_sendCalls (POST /v1/wallets/{id}/rpc) が要求する識別子で、
wallet-connect 時に frontend の Privy SDK から受領して保存する。

非破壊・追加のみ。NULL = 未取得 (旧ユーザー / 非 Privy 経路)。unique 制約なし
(内部識別子であり検索キーにしないため。将来必要なら別 migration で index 追加)。

参照: app/proposals/router.py _resolve_privy_wallet_id / app/proposals/scw_executor.py
      （既存コードは user.privy_wallet_id を優先し、無ければ PRIVY_DELEGATED_WALLET_ID にフォールバック）

Revision ID: pw20260705
Revises: pp20260624
Create Date: 2026-07-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pw20260705"
down_revision: Union[str, Sequence[str], None] = "pp20260624"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add privy_wallet_id column to users table."""
    op.add_column(
        "users",
        sa.Column("privy_wallet_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove privy_wallet_id column from users table."""
    op.drop_column("users", "privy_wallet_id")
