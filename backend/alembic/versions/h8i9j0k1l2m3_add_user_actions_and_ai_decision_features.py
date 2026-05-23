"""add_user_actions_and_ai_decision_features

P0-6 (Hermes 受け入れ前提の学習データ層):
  Hermes 学習に必要な「特徴量」と「ユーザ行動」を蓄積するための 2 表を追加する。

  - user_actions:
      manual UI / onboarding 経由でのユーザ click を supervised signal として
      蓄積する。後段の学習データ抽出 (scripts/export_learning_data.py) で
      ai_decisions と session/時刻で結合し、判定 → 行動の系列を学習データ化する。

  - ai_decision_features:
      ai_decisions と 1:1 で、判定時点のマーケット/ポートフォリオ特徴量を
      正規化して保存する (prompt 入力の再現性を担保)。
      ai_decisions.rag_context_json は既存のまま残し、本表は高頻度クエリ用に
      分離する (docs/50_phase2_ai_optimizer_design.md §9 参照)。

  既存資産との関係:
    portfolio_snapshots (backend/app/portfolio/models.py:18) は変更しない。
    ai_decisions (backend/app/ai/models.py:14) も変更しない。
    本 migration は新規表 2 つの create_table のみで、既存表に touch しない。

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-05-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_actions and ai_decision_features tables."""
    # ------------------------------------------------------------------
    # user_actions: manual UI / onboarding click ログ (supervised signal)
    # ------------------------------------------------------------------
    op.create_table(
        "user_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "action_type",
            sa.String(length=64),
            nullable=False,
            comment="e.g. manual_buy_click, manual_sell_click, onramp_completed",
        ),
        sa.Column(
            "target_type",
            sa.String(length=32),
            nullable=True,
            comment="e.g. proposal, asset",
        ),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column(
            "clicked_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("context_json", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_actions_user_clicked",
        "user_actions",
        ["user_id", "clicked_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_actions_action_type",
        "user_actions",
        ["action_type"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # ai_decision_features: ai_decisions と 1:1 の特徴量保存
    # ------------------------------------------------------------------
    op.create_table(
        "ai_decision_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ai_decision_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("market_apy_supply", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("market_apy_borrow", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("health_factor", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("gas_gwei", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("price_usd", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("prompt_features_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"]),
        sa.ForeignKeyConstraint(["portfolio_snapshot_id"], ["portfolio_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ai_decision_features_decision",
        "ai_decision_features",
        ["ai_decision_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the two learning-data tables."""
    op.drop_index("uq_ai_decision_features_decision", table_name="ai_decision_features")
    op.drop_table("ai_decision_features")
    op.drop_index("ix_user_actions_action_type", table_name="user_actions")
    op.drop_index("ix_user_actions_user_clicked", table_name="user_actions")
    op.drop_table("user_actions")
