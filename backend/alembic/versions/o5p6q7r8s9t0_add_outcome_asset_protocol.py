"""add_outcome_asset_protocol

Layer 2 outcome labeling: ai_decision_outcomes に asset / protocol 列を追加する。
将来 ETH / Aave V4 / Lido / Pendle 等を追加する際にスキーマ変更が最小で済むよう
最初から識別列を持たせる (DoD ★将来拡張設計)。

  asset    VARCHAR(10) DEFAULT 'USDC'     — 対象資産 (USDC / USDT / ETH / WBTC …)
  protocol VARCHAR(20) DEFAULT 'aave_v3' — 対象プロトコル (aave_v3 / aave_v4 / lido …)

既存行は server_default によって即時に 'USDC' / 'aave_v3' が埋まる。

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, Sequence[str], None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_decision_outcomes",
        sa.Column(
            "asset",
            sa.String(length=10),
            nullable=True,
            server_default="USDC",
            comment="対象資産 (USDC/USDT/ETH/WBTC …)",
        ),
    )
    op.add_column(
        "ai_decision_outcomes",
        sa.Column(
            "protocol",
            sa.String(length=20),
            nullable=True,
            server_default="aave_v3",
            comment="対象プロトコル (aave_v3/aave_v4/lido/pendle …)",
        ),
    )
    op.create_index(
        "ix_ai_decision_outcomes_horizon",
        "ai_decision_outcomes",
        ["decision_id", "horizon_hours"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_decision_outcomes_horizon", table_name="ai_decision_outcomes")
    op.drop_column("ai_decision_outcomes", "protocol")
    op.drop_column("ai_decision_outcomes", "asset")
