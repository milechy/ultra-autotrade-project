# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""create_chat_messages_table

チャット会話保存 (GID: 1215648108179500) 用の chat_messages テーブルを作成する。

スキーマは backend/app/chat/models.py の ChatMessage を真実源とする:
- role CHECK ('user', 'ai') — models.py の ck_chat_messages_role と一致 (二重管理ルール準拠)
- 複合 index idx_chat_messages_user_created (user_id, created_at DESC)
  — WHERE user_id = ? ORDER BY created_at DESC クエリ用

冪等: main.py が Base.metadata.create_all() でも本テーブルを作成するため、
既存環境では has_table で存在確認してから作成する (b3invtbl9k0z と同パターン)。

Revision ID: cm20260612
Revises: db20260612
Create Date: 2026-06-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "cm20260612"
down_revision: Union[str, Sequence[str], None] = "db20260612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """chat_messages テーブルと複合 index を作成する。"""
    bind = op.get_bind()
    if inspect(bind).has_table("chat_messages"):
        # 既存環境では create_all / 手動 DDL で既に存在する。再作成しない。
        return
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'ai')", name="ck_chat_messages_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_chat_messages_user_created",
        "chat_messages",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """chat_messages テーブルを削除する。"""
    bind = op.get_bind()
    if not inspect(bind).has_table("chat_messages"):
        return
    op.drop_index("idx_chat_messages_user_created", table_name="chat_messages")
    op.drop_table("chat_messages")
