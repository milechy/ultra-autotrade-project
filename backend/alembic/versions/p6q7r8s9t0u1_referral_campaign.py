"""referral_campaign and uat_wallet_ledger tables

紹介キャンペーン仕様変更に伴い 2 テーブルを追加:
- referral_campaigns : パートナーごとの紹介ウィンドウ (最新1件が有効)
- uat_wallet_ledger  : UAT 収支台帳 (月次バッチで credit/debit を記録)

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-06-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, Sequence[str], None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("""
            CREATE TABLE IF NOT EXISTS referral_campaigns (
                id BIGSERIAL PRIMARY KEY,
                partner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                referree_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reward_start_month DATE NOT NULL,
                reward_expires_month DATE NOT NULL,
                ended_early_month DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_rc_referree_month "
            "ON referral_campaigns (referree_id, reward_start_month, reward_expires_month)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_rc_partner "
            "ON referral_campaigns (partner_id)"
        )

        op.execute("""
            CREATE TABLE IF NOT EXISTS uat_wallet_ledger (
                id BIGSERIAL PRIMARY KEY,
                entry_type VARCHAR(16) NOT NULL,
                amount_jpy NUMERIC(18,2) NOT NULL,
                reason VARCHAR(64) NOT NULL,
                reference_fee_tx_id BIGINT REFERENCES fee_transactions(id) ON DELETE SET NULL,
                month DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT chk_uwl_entry_type CHECK (entry_type IN ('credit', 'debit')),
                CONSTRAINT chk_uwl_amount CHECK (amount_jpy >= 0)
            )
        """)
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_uwl_fee_tx_type_reason "
            "ON uat_wallet_ledger (reference_fee_tx_id, entry_type, reason) "
            "WHERE reference_fee_tx_id IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_uwl_month "
            "ON uat_wallet_ledger (month)"
        )
    else:
        # SQLite (テスト環境)
        op.create_table(
            "referral_campaigns",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "partner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "referree_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("reward_start_month", sa.Date(), nullable=False),
            sa.Column("reward_expires_month", sa.Date(), nullable=False),
            sa.Column("ended_early_month", sa.Date(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_table(
            "uat_wallet_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entry_type", sa.String(16), nullable=False),
            sa.Column("amount_jpy", sa.Numeric(18, 2), nullable=False),
            sa.Column("reason", sa.String(64), nullable=False),
            sa.Column(
                "reference_fee_tx_id",
                sa.Integer(),
                sa.ForeignKey("fee_transactions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("month", sa.Date(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("DROP TABLE IF EXISTS uat_wallet_ledger")
        op.execute("DROP TABLE IF EXISTS referral_campaigns")
    else:
        op.drop_table("uat_wallet_ledger")
        op.drop_table("referral_campaigns")
