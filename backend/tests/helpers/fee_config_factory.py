# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/helpers/fee_config_factory.py
"""F-4 seed と同等の DB 未保存 ``FeeConfigV10`` factory。

F-5 計算ロジックのユニットテストで使用する。F-4 ``build_v10_default_config()``
と同じ値を返すが、DB 接続は不要。

values は v10 spec §1 と一致 (PR #125 で staging-new 投入確認済み):
- tier_thresholds_jpy:     [1_000_000, 10_000_000]
- tier_fee_rates:          [0.30, 0.25, 0.20]
- tier_monthly_yield_caps: [0.018, 0.023, 0.030]
- subscription_rates:      {"conservative": 0.0, "balanced": 0.003, "aggressive": 0.01}
- affiliate_rate:          0.10  (紹介報酬 = 紹介友達の実受取利益 × 10%, Asana 1215467015333283 / seed と一致)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.fees.models import FeeConfigV10

#: JST タイムゾーン (effective_from の TZ 一致用)。
_JST = timezone(timedelta(hours=9))


def make_v10_default_config() -> FeeConfigV10:
    """F-4 seed と同じ値の DB 未保存 ``FeeConfigV10`` instance を返す。

    DB セッション不要のため、純粋関数テスト (FeeCalculator) で利用可。
    """
    return FeeConfigV10(
        config_name="v10_default",
        tier_thresholds_jpy=[1_000_000, 10_000_000],
        tier_fee_rates=[0.30, 0.25, 0.20],
        tier_monthly_yield_caps=[0.018, 0.023, 0.030],
        subscription_rates={
            "conservative": 0.0,
            "balanced": 0.003,
            "aggressive": 0.01,
        },
        expense_markup_enabled=False,
        expense_markup_rate=Decimal("0"),
        affiliate_rate=Decimal("0.10"),
        is_active=True,
        effective_from=datetime(2026, 5, 1, tzinfo=_JST),
    )
