"""add gas_sponsored column to transactions

実ガス代記録 (bundler eth_getUserOperationReceipt の actualGasUsed/actualGasCost) を
transactions.gas_used / gas_price_gwei (既存カラム) に格納するのに合わせ、paymaster
スポンサー有無を判別するための gas_sponsored 列を追加する。
True=paymasterスポンサー全額負担 / False=Smart Wallet自己負担 / NULL=判別不能
(EOA経路・bundlerがpaymasterを返さない場合。部分スポンサーはall-or-nothing扱い)。
詳細: backend/app/transactions/models.py 冒頭コメント参照。

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("gas_sponsored", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "gas_sponsored")
