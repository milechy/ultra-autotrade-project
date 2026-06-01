"""add_invitation_type

invitations テーブルへの変更（open registration mode 対応）:
  - type 列追加: VARCHAR(10) DEFAULT 'invite' (open | invite)
  - partner_id を nullable 変更: open 登録時は partner 不要

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-06-01 00:00:00.000000

既存 invitations レコードは type='invite' (server_default) で自動補完されるため後方互換。
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # invitations.type 列追加 (open | invite)
    op.add_column(
        "invitations",
        sa.Column(
            "type",
            sa.String(10),
            nullable=False,
            server_default="invite",
        ),
    )
    # partner_id を nullable に変更 (open 招待は partner 不要)
    op.alter_column(
        "invitations",
        "partner_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # partner_id を NOT NULL に戻す (open レコードは NULL なので手動対処が必要)
    op.alter_column(
        "invitations",
        "partner_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("invitations", "type")
