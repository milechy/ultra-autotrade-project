"""execution_policy_safe_default

P0 GID 1214993061793196 (P3-1):
  新規ユーザーの execution_policy DB default を auto_execute → require_approval に変更。

  金融システムの安全既定は require_approval であるべき。
  role default=VIEWER + execution_policy default=auto_execute の組み合わせで
  「明示設定なし user が viewer+auto_execute」となる設計違反を修正する。

  既存の auto_execute 行 (id=7/8/17 等) の UPDATE は本マイグレーション対象外。
  既存行の変更は別途 P0 対応 UPDATE で実施する。

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change users.execution_policy DB default from auto_execute to require_approval.

    This only affects newly inserted rows where execution_policy is not explicitly set.
    Existing rows with auto_execute are NOT updated by this migration.
    """
    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'require_approval'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert users.execution_policy DB default back to auto_execute."""
    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'auto_execute'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
