# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_smart_wallet_address

users に smart_wallet_address (ERC-4337 Smart Wallet アドレス) を追加する。
Privy Smart Wallet AA + paymaster 移行 設計 doc §6.2 スライス3a（hkobayashi 承認 2026-06-18）。

非破壊・追加のみ。列は slice3b（submit-tx 配線）で使うまで未使用（NULL = 全員 EOA 経路のまま）。
NULL = EOA ユーザー / 設定済 = Smart Wallet ユーザー という判別子になる。

wallet_address (b2c3d4e5f6a7) と同じく String(42) / nullable / unique。

Revision ID: swa20260618
Revises: m4h20260618
Create Date: 2026-06-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "swa20260618"
down_revision: Union[str, Sequence[str], None] = "m4h20260618"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add smart_wallet_address column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "smart_wallet_address",
            sa.String(length=42),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_users_smart_wallet_address", "users", ["smart_wallet_address"])
    op.create_index(
        "ix_users_smart_wallet_address",
        "users",
        ["smart_wallet_address"],
        unique=True,
    )


def downgrade() -> None:
    """Remove smart_wallet_address column from users table."""
    op.drop_index("ix_users_smart_wallet_address", table_name="users")
    op.drop_constraint("uq_users_smart_wallet_address", "users", type_="unique")
    op.drop_column("users", "smart_wallet_address")
