"""fee_configs.affiliate_rate column DEFAULT 0.30 -> 0.10

紹介報酬仕様 (Asana 1215467015333283 / 2026-06-06 確定) の確定により、affiliate_rate は
「紹介友達の月次 user_takehome_jpy の 10%」を意味する。列 DEFAULT が旧 0.30 (サブスク料基準
時代の値) のままだと、新規 fee_configs INSERT が誤った 0.30 で作られ得るため 0.10 に揃える。

- 本 migration は **列 DEFAULT (今後の INSERT 用) のみ** を変更する。
- 既存行 (現行 active config) の値是正は ops 子タスク 1215466962382625 (人間) が担当。
- model 側 (FeeConfigV10.affiliate_rate.server_default) は既に 0.10 でドリフトしていたのを解消。

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-06-07 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite (テスト) は ALTER COLUMN ... SET DEFAULT 非対応 + そもそも model server_default
    # =0.10 を使うため no-op。PostgreSQL のみ列 DEFAULT を是正する。
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE fee_configs ALTER COLUMN affiliate_rate SET DEFAULT 0.10")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE fee_configs ALTER COLUMN affiliate_rate SET DEFAULT 0.30")
