# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""merge_four_heads

alembic head が 4 本に分岐していたため、merge migration で 1 本に統合する。
m3h20260609（3-head 統合, 2026-06-09）以降に並行マージされた 4 本の feature migration が
それぞれ head 統合をしなかった結果、再び multi-head 化していた。

統合対象 head:
  - s9t0u1v2w3x4  (add_proposals_expiry_reminder_sent)
  - b3invtbl9k0z  (create_invitations_table)
  - cm20260612    (create_chat_messages_table)
  - w3x4y5z6a7b8  (add_account_deletion_requests)

`alembic upgrade head` が "Multiple head revisions present" で停止する状態だった。
deploy_production.sh は upgrade head 失敗時にデプロイを中止する設計のため、
backend デプロイの前提ブロッカー。本 migration はスキーマ変更を伴わない統合のみ。

Revision ID: m4h20260618
Revises: s9t0u1v2w3x4, b3invtbl9k0z, cm20260612, w3x4y5z6a7b8
Create Date: 2026-06-18 00:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "m4h20260618"
down_revision: Union[str, Sequence[str], None] = (
    "s9t0u1v2w3x4",
    "b3invtbl9k0z",
    "cm20260612",
    "w3x4y5z6a7b8",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """head 統合のみ。スキーマ変更なし。"""
    pass


def downgrade() -> None:
    """統合前の 4 head 状態に戻す。スキーマ変更なし。"""
    pass
