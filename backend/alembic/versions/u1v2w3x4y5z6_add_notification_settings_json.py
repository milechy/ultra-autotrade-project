# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""add_notification_settings_json

users テーブルに notification_settings_json (TEXT, nullable) を追加する (Lane C2+E)。

チャネル (LINE / PWA push) および通知種別 (ai_proposal / execution_complete 等) の
per-user 設定を JSON テキストとして永続化する。NULL はデフォルト設定を意味する。

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-06-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users.notification_settings_json を追加する。"""
    op.add_column(
        "users",
        sa.Column("notification_settings_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """users.notification_settings_json を削除する。"""
    op.drop_column("users", "notification_settings_json")
