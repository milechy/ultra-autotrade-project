"""create_invitations_table (pre-j0k1 baseline)

invitations テーブルの create migration を補完する。

背景:
  invitations モデル (app/invitations/models.py) は本番では手動 DDL / create_all で
  作成されてきた (§12 / 2026-04-05 教訓「DB マイグレーションは手動 ALTER TABLE 方式」)。
  そのため create migration が alembic chain に存在せず、後続の
  j0k1l2m3n4o5 (add_invitation_type) が ALTER 対象テーブル不在で fresh DB upgrade を
  止めていた。本 migration を j0k1 の直前に挿入し chain を自己完結させる。

本番影響:
  本番 alembic_version は o5p6q7r8s9t0 で stamp 済み。本 revision はその祖先
  (i9j0k1l2m3n4 と j0k1l2m3n4o5 の間) のため、本番 `alembic upgrade head` では
  適用済み扱いとなり実行されない (安全)。fresh DB / 本番相当 DB 構築時のみ実行される。

スキーマは j0k1 適用「前」の状態 (type 列なし / partner_id NOT NULL)。
j0k1 が後段で type 追加 + partner_id nullable 化を行う。

冪等: 既存テーブルがある環境でも安全なよう has_table で存在確認してから作成する。

Revision ID: b3invtbl9k0z
Revises: i9j0k1l2m3n4
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "b3invtbl9k0z"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("invitations"):
        # 本番 / 既存環境では手動 DDL / create_all で既に存在する。再作成しない。
        return
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column(
            "partner_id",
            sa.Integer(),
            nullable=False,  # j0k1l2m3n4o5 で nullable 化される (open registration)
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["partner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_code", "invitations", ["code"], unique=True)
    op.create_index("ix_invitations_partner_id", "invitations", ["partner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("invitations"):
        return
    op.drop_index("ix_invitations_partner_id", table_name="invitations")
    op.drop_index("ix_invitations_code", table_name="invitations")
    op.drop_table("invitations")
