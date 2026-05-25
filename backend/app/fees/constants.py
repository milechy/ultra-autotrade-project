# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/constants.py
"""Fee Model v10 launch 値の Single Source Of Truth (P0-18)。

`scripts/seed_fee_config_v10.py` と `docs/ops/fee_model_v10.md` の数値が
過去ドリフトしていたため、本 module に集約する。値変更時の更新先:
1. 本ファイル
2. `docs/ops/fee_model_v10.md` (人間向け解説 + 数値表)
3. `scripts/seed_fee_config_v10.py` (本 module を import すれば自動同期)

設計:
- 値は plain Python 型 (list[int], list[float], Decimal)。
- ``Decimal`` は固定小数の比率にのみ使う (gas/expense)。
- list は **MIDDLE / UPPER の monotonicity (tier_thresholds, yield_caps)** を満たす。
  - tier_fee_rates は monotonic DECREASING (上位ティアほど低料率)。
- 整合性 invariant は ``tests/fees/test_constants.py`` で機械検査。
"""

from __future__ import annotations

from decimal import Decimal

#: tier 境界 (JPY)。len == 2、LOWER と MIDDLE / MIDDLE と UPPER の境界。
#: LOWER: ~1,000,000 円、MIDDLE: 1,000,001 ~ 10,000,000 円、UPPER: 10,000,001 円~。
TIER_THRESHOLDS_JPY: list[int] = [1_000_000, 10_000_000]

#: tier ごとの月次手数料率。LOWER / MIDDLE / UPPER の順 (3 要素)。
#: 上位ティアほど低率。Decimal ではなく float で保持しているのは fee_configs の
#: JSONB カラムが list[float] 型のため。Decimal 化は将来検討。
TIER_FEE_RATES: list[float] = [0.30, 0.25, 0.20]

#: tier ごとの月次最大利回り cap。LOWER / MIDDLE / UPPER の順 (3 要素)。
#: 1.8% / 2.3% / 3.0%。上位ほど高 cap (リスク許容拡大)。
TIER_MONTHLY_YIELD_CAPS: list[float] = [0.018, 0.023, 0.030]

#: アフィリエイト還元率 (固定 30%)。
AFFILIATE_RATE: Decimal = Decimal("0.30")

#: 旧 v9 経費マークアップ率 (v10 では既定 OFF)。
EXPENSE_MARKUP_ENABLED_DEFAULT: bool = False
EXPENSE_MARKUP_RATE_DEFAULT: Decimal = Decimal("0")


__all__ = [
    "TIER_THRESHOLDS_JPY",
    "TIER_FEE_RATES",
    "TIER_MONTHLY_YIELD_CAPS",
    "AFFILIATE_RATE",
    "EXPENSE_MARKUP_ENABLED_DEFAULT",
    "EXPENSE_MARKUP_RATE_DEFAULT",
]
