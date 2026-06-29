# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/deposit_policy.py

"""ユーザー運用開始の最低入金額ポリシー（単一の真実源 / single source of truth）。

`MIN_DEPOSIT_USD` は「自動運用を開始するための最低入金額（USD）」を表す唯一の正本。
A-2 のバックエンド実行時ゲート（提案生成 / 提案承認 / モード切替）は、残高による
運用開始可否を判定する際、ハードコードした数値ではなく必ず本モジュールを参照すること。
env `MIN_DEPOSIT_USD` で上書き可能（デフォルト 200）。

[混同注意] 以下は名前が似ているが別概念であり、本ポリシーと取り違えないこと:
- `ai_judgment_scheduler._PROPOSAL_AMOUNT_MIN_USD`（既定 $50）
    1 提案あたりの最小サイジング額（提案金額の下限）であって、運用開始の入金ゲートではない。
- frontend `MINIMUM_USD_BALANCE`（$3000, lib/web3/config.ts）
    参考表示用の「推奨運用額」。ブロックには使わない（informational only）。

金融計算ルール（CLAUDE.md [CRITICAL] 11）に従い Decimal 型のみを使う。
"""

import os
from decimal import Decimal
from typing import Optional

# 運用開始の最低入金額（USD）。env で上書き可能。これが唯一の正本。
MIN_DEPOSIT_USD: Decimal = Decimal(os.getenv("MIN_DEPOSIT_USD", "200"))


def meets_minimum_deposit(balance_usd: Optional[Decimal]) -> bool:
    """残高が運用開始の最低入金額を満たすか判定する。

    Args:
        balance_usd: 評価対象の残高（USD）。取得不能（None）は安全側に倒して False。

    Returns:
        balance_usd が `MIN_DEPOSIT_USD` 以上なら True。None なら False。
    """
    if balance_usd is None:
        return False
    return balance_usd >= MIN_DEPOSIT_USD
