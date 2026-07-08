"""add stripe_customer_id / stripe_default_payment_method_id to users

月額サブスク課金 (F-7 Stripe 統合)。stripe_customer_id は Stripe Customer ID、
stripe_default_payment_method_id は off-session 課金に使う既定カードの PaymentMethod ID。

Revision ID: x4y5z6a7b8c9
Revises: pw20260705
Create Date: 2026-07-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "pw20260705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_users_stripe_customer_id",
        "users",
        ["stripe_customer_id"],
        unique=True,
        postgresql_where=sa.text("stripe_customer_id IS NOT NULL"),
    )
    op.add_column(
        "users",
        sa.Column("stripe_default_payment_method_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "stripe_default_payment_method_id")
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "stripe_customer_id")
