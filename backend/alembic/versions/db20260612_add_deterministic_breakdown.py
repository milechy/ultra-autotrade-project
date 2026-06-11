# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_deterministic_breakdown_to_ai_decision_features

ai_decision_features テーブルに deterministic_breakdown (JSONB, nullable) を追加する
(EPIC-1 1-6 / 4軸 Shadow consensus 用)。

設計書 docs/52 の judgment_logs テーブルは実在しない (実体は JSONL ロガー) ため、
承認済み読み替えで実 DB sink の ai_decision_features に追加する。4軸 Shadow consensus の
決定論的内訳 (各軸スコア/重み) を格納する。NULL 許容 (fail-open)。Shadow 書込配線は後続 PR-3 (1-7)。

CHECK 制約は付けない (models.py が真実源ルール / JSONB に enum CHECK 不要)。

Revision ID: db20260612
Revises: m3h20260609
Create Date: 2026-06-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "db20260612"
down_revision: Union[str, Sequence[str], None] = "m3h20260609"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """ai_decision_features.deterministic_breakdown を追加する。"""
    op.add_column(
        "ai_decision_features",
        sa.Column(
            "deterministic_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """ai_decision_features.deterministic_breakdown を削除する。"""
    op.drop_column("ai_decision_features", "deterministic_breakdown")
