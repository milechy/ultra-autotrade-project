# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""merge_three_heads

alembic head が 3 本に分岐していたため、merge migration で 1 本に統合する。

統合対象 head:
  - 6a2621bd89  (add_proposals_expiry_reminder_sent / down=n4o5p6q7r8s9)
  - cfm1corp2month  (add_corporate_fiscal_month / down=u1v2w3x4y5z6)
  - v2w3x4y5z6a7  (affiliate_rate_default_010 / down=u1v2w3x4y5z6)

並行開発で notif settings (u1v2w3x4y5z6) に 2 子がぶら下がり、加えて
expiry_reminder_sent rail が別系統 (n4o5p6q7r8s9 起点) で分岐していたため、
`alembic upgrade head` が "Multiple head revisions present" で停止する状態だった。
deploy_production.sh は upgrade head 失敗時にデプロイを中止する設計のため、
backend デプロイの前提ブロッカー。本 migration はスキーマ変更を伴わない統合のみ。

Revision ID: m3h20260609
Revises: 6a2621bd89, cfm1corp2month, v2w3x4y5z6a7
Create Date: 2026-06-09 07:40:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "m3h20260609"
down_revision: Union[str, Sequence[str], None] = (
    "6a2621bd89",
    "cfm1corp2month",
    "v2w3x4y5z6a7",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """head 統合のみ。スキーマ変更なし。"""
    pass


def downgrade() -> None:
    """統合前の 3 head 状態に戻す。スキーマ変更なし。"""
    pass
