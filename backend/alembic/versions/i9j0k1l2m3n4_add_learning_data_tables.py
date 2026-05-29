"""add_learning_data_tables

Hermes 学習 Phase 0 capture (Asana 1215219987634293):
  3 テーブルを追加する。h8i9j0k1l2m3 (add_proposals_execution_attempts) の次を取る
  ことで main の二重採番コンフリクトを解消する。

  - user_actions:
      manual UI / onboarding 経由でのユーザ click を supervised signal として蓄積。
      後段の学習データ抽出で ai_decisions と結合し判定→行動系列を学習データ化する。

  - ai_decision_features:
      ai_decisions と 1:1 で判定時点の特徴量を保存する。
      特徴量棚卸し: utilization_rate/supply_apy/borrow_apy/health_factor は
      fetch_aave_market_data_safe() で取得可能。RSI/MACD/volatility/gas は現コードに
      存在しないため本テーブルに列を持たない (NULL確定列は追加しない)。
      agent_signals jsonb: 4エージェント (indicator/pattern/risk/macro) の
      bias+confidence+key_data を保存 (service.py の run_all_agents() 結果)。
      raw_features jsonb: Aave raw 数値 + geo_risk/fed_stance/stablecoin_risk。
      embedding: text-embedding-3-small 1536次元 (pgvector)。NULL許容 (fail-open)。

  - ai_decision_outcomes:
      列定義のみ。Phase 1 バッチで後付け入力する realized_yield_delta 等。
      partner_approved は承認/却下時に proposals/router.py から即時 capture。

  既存テーブルは変更しない。

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-05-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

try:
    import pgvector.sqlalchemy  # noqa: F401  # available on PostgreSQL envs
except ImportError:
    pgvector = None  # type: ignore[assignment]

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    #
    # 列選定方針: 判定時に実際に取得できる値のみ。NULL確定の RSI/MACD/gas 等は含めない。
    # ------------------------------------------------------------------
    op.create_table(
        "ai_decision_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ai_decision_id", sa.Integer(), nullable=False),
        # 4エージェント (indicator/pattern/risk/macro) の bias+confidence+key_data
        sa.Column("agent_signals", postgresql.JSONB(), nullable=True),
        # Aave raw + geo_risk/fed_stance/stablecoin_risk の実測値
        sa.Column("raw_features", postgresql.JSONB(), nullable=True),
        # 最終判定アクション (BUY/SELL/HOLD)
        sa.Column("judge_action", sa.String(length=10), nullable=False),
        # 最終信頼度スコア (0-100)
        sa.Column("confidence", sa.Integer(), nullable=False),
        # primary と secondary が一致したか
        sa.Column("cross_verify", sa.Boolean(), nullable=False),
        # text-embedding-3-small 1536次元。pgvector が利用可能な場合のみ有効。NULL許容。
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.vector.VECTOR(dim=1536) if pgvector else sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ai_decision_features_decision",
        "ai_decision_features",
        ["ai_decision_id"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # ai_decision_outcomes: Phase 1 バッチが書き込む実績データ
    # partner_approved は承認/却下エンドポイントから即時 INSERT する。
    # 他列は Phase 1 まで NULL のまま（列定義のみ）。
    # ------------------------------------------------------------------
    op.create_table(
        "ai_decision_outcomes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=True),
        sa.Column(
            "realized_yield_delta",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
        ),
        sa.Column("gas_cost_usd", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("hf_min_after", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("partner_approved", sa.Boolean(), nullable=True),
        sa.Column("regret_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("is_positive_example", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["ai_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_decision_outcomes_decision",
        "ai_decision_outcomes",
        ["decision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_decision_outcomes_decision", table_name="ai_decision_outcomes")
    op.drop_table("ai_decision_outcomes")
    op.drop_index("uq_ai_decision_features_decision", table_name="ai_decision_features")
    op.drop_table("ai_decision_features")
    op.drop_index("ix_user_actions_action_type", table_name="user_actions")
    op.drop_index("ix_user_actions_user_clicked", table_name="user_actions")
    op.drop_table("user_actions")
