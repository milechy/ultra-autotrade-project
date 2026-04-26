"""Add privy_did to users and make hashed_password nullable

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-05-03 00:00:00.000000

このファイルは「案」です。alembic/versions/ に配置しないこと。
実行は Asana GID 1214176336328111 (2026-05-03予定) で実施。

実行前提条件:
  - 全既存ユーザーが hashed_password IS NOT NULL であること
    確認: SELECT COUNT(*) FROM users WHERE hashed_password IS NULL; → 0

実施手順詳細:
  docs/integration/db_alter_users_privy.md §8 チェックリスト参照

ダウンタイム見積もり: < 100ms (6ユーザー規模)
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op  # noqa: E402

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (A) hashed_password を nullable に変更（メタデータ変更のみ、即時完了）
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # (B) privy_did カラム追加
    op.add_column(
        "users",
        sa.Column("privy_did", sa.String(length=255), nullable=True),
    )

    # (B) privy_did にパーシャルユニークインデックス (NULL は除外)
    op.create_index(
        "ix_users_privy_did",
        "users",
        ["privy_did"],
        unique=True,
        postgresql_where=sa.text("privy_did IS NOT NULL"),
    )

    # (C) CHECK制約: hashed_password と privy_did のどちらか一方は必須
    # 既存行は全て hashed_password IS NOT NULL なので制約違反は起きない
    op.create_check_constraint(
        "chk_users_auth_method",
        "users",
        "hashed_password IS NOT NULL OR privy_did IS NOT NULL",
    )


def downgrade() -> None:
    # (C) CHECK制約削除
    op.drop_constraint("chk_users_auth_method", "users", type_="check")

    # (B) インデックス + カラム削除
    op.drop_index("ix_users_privy_did", table_name="users")
    op.drop_column("users", "privy_did")

    # (A) hashed_password を NOT NULL に戻す
    # 警告: privy_did のみのユーザー (hashed_password IS NULL) が存在する場合は失敗する。
    # その場合は手動で hashed_password をランダム値で埋めてから実行すること。
    # 詳細: docs/integration/db_alter_users_privy.md §4 ロールバック手順
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
