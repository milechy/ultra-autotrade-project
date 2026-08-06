"""reapply execution_policy safe default (auto_execute -> require_approval)

新規ユーザーの `users.execution_policy` DB default を安全側 (require_approval) に戻す。

## なぜ「再適用」が必要か

`g7h8i9j0k1l2_execution_policy_safe_default.py` が同じ ALTER DEFAULT を行っており、
その revision は head の祖先＝**適用済みのはず**である
(`a7b8c9d0e1f2 -> g7h8i9j0k1l2 -> h8i9j0k1l2m3` のチェーン上)。
しかし 2026-08-06 の本番実機確認では:

    \\d users → execution_policy ... default 'auto_execute'::character varying

となっており、**alembic_version が head を指しているのに ALTER の効果が実DBに無い**。
同様の乖離が他にも観測されている (いずれも本番実測):

| 対象 | migration の指示 | 本番の実態 |
|---|---|---|
| `execution_policy` default | `require_approval` (g7) | `auto_execute` |
| `users.wallet_address` 型 | `String(42)` (b2c3d4e5f6a7) | `VARCHAR(255)` |
| `ix_users_wallet_address` | UNIQUE index 作成 (同上) | **存在しない** |

つまり過去にDB復元や `create_all()` による再作成の後、migration を実行せずに
`alembic stamp` された可能性が高い。**alembic_version は本番スキーマの実態を
保証しない**という運用上の前提崩れがあり、これは別途調査対象
(本 migration のスコープ外)。

## なぜ g7 を再実行せず新 revision を作るのか

g7 は ALTER DEFAULT に加えて **既存行のバックフィル**を含む:

    UPDATE users SET execution_policy='require_approval' WHERE execution_policy='auto_execute';

g7 の docstring は「現フェーズに正規 auto_execute なし」を前提としているが、
2026-08-06 時点の本番には **意図的に完全おまかせを選んでいるユーザーが 2 名存在する**
(user 11 / 18、いずれも user_mode=managed)。g7 を再実行すると彼らの運用モードを
無断で変更してしまう。これは要件定義
(`docs/internal/2026-08-04_execution_pipeline_requirements.md` I-3 禁止事項 7)
「安全側への自動降格をユーザーに無断で行うと、機能不全を不信に変換するだけ」に該当する。

したがって本 migration は **ALTER DEFAULT のみ**を行い、既存行には一切触れない。
既存行の運用モード変更が必要な場合は、ユーザーへの通知を伴う別プロセスで行う
(到達経路は 2026-08-05 に復旧済み)。

## 冪等性

ALTER COLUMN ... SET DEFAULT は現在値に関わらず同じ結果になるため、
既に require_approval であっても no-op として安全に再実行できる。

## 影響

- 既存行: 変更なし (本番実測で execution_policy IS NULL の行は 0 件)
- 新規行: `execution_policy` 未指定の INSERT が require_approval になる
  (従来は auto_execute = 完全自動執行だった)

Revision ID: a8b9c0d1e2f3
Revises: z7a8b9c0d1e2
Create Date: 2026-08-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "z7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """DB default を require_approval に設定する。既存行は変更しない。

    SQLite は ALTER COLUMN ... SET DEFAULT を持たないためスキップする
    (a7b8c9d0e1f2 等と同じ方言ガードの慣習に従う)。SQLite 利用時は
    models.py 側の Python default (ExecutionPolicy.REQUIRE_APPROVAL) が効くため
    ORM 経由の INSERT では同じ安全側の結果になる。
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'require_approval'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """default を auto_execute に戻す。

    安全側 (require_approval) から危険側 (auto_execute) へ戻す操作であり、
    通常は実行すべきでない。ロールバック手順の完全性のためにのみ定義する。
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'auto_execute'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
