# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/fee_service.py
"""
tier別手数料率サービス。

二層戦略:
  GENERAL: 手数料率 3〜10%（〜$20,000）
  UPPER:   手数料率 15〜25%（$20,000〜）

B-1 で AI Optimizer ENB ベースの動的計算が追加される予定。
C-3 では各ティアの手数料率レンジのみを返す。
"""

from typing import TypedDict


class FeeRateRange(TypedDict):
    """手数料率レンジの型定義。"""

    tier: str
    label: str
    min_rate: str
    max_rate: str
    min_rate_pct: str
    max_rate_pct: str
    description: str


_FEE_SCHEDULE: dict[str, FeeRateRange] = {
    "GENERAL": FeeRateRange(
        tier="GENERAL",
        label="一般",
        min_rate="0.03",
        max_rate="0.10",
        min_rate_pct="3",
        max_rate_pct="10",
        description="運用資産 $20,000 未満のティア",
    ),
    "UPPER": FeeRateRange(
        tier="UPPER",
        label="アッパー",
        min_rate="0.15",
        max_rate="0.25",
        min_rate_pct="15",
        max_rate_pct="25",
        description="運用資産 $20,000 以上のティア",
    ),
}


def get_fee_rate_range(tier: str) -> FeeRateRange:
    """
    ティア文字列から手数料率レンジを返す。

    Args:
        tier: "GENERAL" または "UPPER"

    Returns:
        FeeRateRange dict

    Raises:
        ValueError: 不明なティアを指定した場合
    """
    if tier not in _FEE_SCHEDULE:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {list(_FEE_SCHEDULE)}")
    return _FEE_SCHEDULE[tier]


def get_full_fee_schedule() -> list[FeeRateRange]:
    """
    全ティアの手数料率レンジ一覧を返す（GENERAL → UPPER の順）。
    """
    return [_FEE_SCHEDULE["GENERAL"], _FEE_SCHEDULE["UPPER"]]
