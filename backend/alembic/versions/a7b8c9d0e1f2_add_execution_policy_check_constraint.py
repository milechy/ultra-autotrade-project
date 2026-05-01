"""add_execution_policy_check_constraint_and_default

Add CHECK constraint on users.execution_policy to enforce the three valid
ExecutionPolicy values, preventing future drift between code and DB state.

Background (GID 1214176344039867, P1):
- staging users で execution_policy = 'shadow' のような無効値が紛れ込んでいた
- a1b2c3d4e5f6 で server_default = 'auto_execute' は既に設定済みだが、
  DB レベルの値検証が欠落しており、API バリデーションを回避すると不正値が入る
- ExecutionPolicy enum (app.auth.constants) と DB CHECK を同期させる

Idempotent: 既に同名の制約が存在する場合はスキップする (本番 SQL 直適用済みケース対策)。

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "users_execution_policy_check"
VALID_POLICIES = ("auto_execute", "require_approval", "proposal_only")


def upgrade() -> None:
    """Add CHECK constraint on users.execution_policy.

    server_default は a1b2c3d4e5f6 で既に 'auto_execute' に設定済み。
    本マイグレーションでは CHECK 制約のみを追加する。

    Sanitize step (Codex P1): 無効値を持つ行を先に修正してから ADD CONSTRAINT する。
    ADD CONSTRAINT は既存行に対して即座に検証するため、無効値が残っていると失敗する。
    フォールバック先: 'require_approval' (最も安全な既定値)。
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 無効な execution_policy を持つ行を有効値に修正してから制約を追加する
        values_sql = ", ".join(f"'{v}'" for v in VALID_POLICIES)
        op.execute(
            f"UPDATE users SET execution_policy = 'require_approval' "
            f"WHERE execution_policy NOT IN ({values_sql})"
        )
        # 既存制約があれば一旦削除してから再作成 (idempotent + 値リスト変更にも追随)
        op.execute(
            f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}",
        )
        op.execute(
            f"ALTER TABLE users ADD CONSTRAINT {CONSTRAINT_NAME} "
            f"CHECK (execution_policy IN ({values_sql}))"
        )
    else:
        # SQLite 等は batch mode で対応 (テスト用 fallback)
        with op.batch_alter_table("users") as batch_op:
            values_sql = ", ".join(f"'{v}'" for v in VALID_POLICIES)
            batch_op.create_check_constraint(
                CONSTRAINT_NAME,
                f"execution_policy IN ({values_sql})",
            )


def downgrade() -> None:
    """Remove CHECK constraint on users.execution_policy."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}",
        )
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
