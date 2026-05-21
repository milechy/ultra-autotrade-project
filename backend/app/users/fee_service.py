# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/fee_service.py
"""
tier 別手数料率サービス。

v10 三層戦略 (F-2 2026-04-25 〜):
  LOWER:  手数料率 3〜10% (〜100 万円)
  MIDDLE: 手数料率 8〜18% (100 万〜1000 万円)
  UPPER:  手数料率 15〜25% (1000 万円〜)
"""

from typing_extensions import TypedDict


class FeeRateRange(TypedDict):
    """手数料率レンジの型定義。"""

    tier: str
    label: str
    min_rate: str
    max_rate: str
    min_rate_pct: str
    max_rate_pct: str
    description: str


_LOWER = FeeRateRange(
    tier="LOWER",
    label="一般",
    min_rate="0.03",
    max_rate="0.10",
    min_rate_pct="3",
    max_rate_pct="10",
    description="デポジット 100 万円以下のティア",
)
_MIDDLE = FeeRateRange(
    tier="MIDDLE",
    label="ミドル",
    min_rate="0.08",
    max_rate="0.18",
    min_rate_pct="8",
    max_rate_pct="18",
    description="デポジット 100 万〜1000 万円のティア",
)
_UPPER = FeeRateRange(
    tier="UPPER",
    label="アッパー",
    min_rate="0.15",
    max_rate="0.25",
    min_rate_pct="15",
    max_rate_pct="25",
    description="デポジット 1000 万円以上のティア",
)

_FEE_SCHEDULE: dict[str, FeeRateRange] = {
    "LOWER": _LOWER,
    "MIDDLE": _MIDDLE,
    "UPPER": _UPPER,
}


def get_fee_rate_range(tier: str) -> FeeRateRange:
    """ティア文字列から手数料率レンジを返す。

    Args:
        tier: "LOWER" / "MIDDLE" / "UPPER"

    Returns:
        FeeRateRange dict

    Raises:
        ValueError: 不明なティアを指定した場合
    """
    if tier not in _FEE_SCHEDULE:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {sorted(_FEE_SCHEDULE)}")
    return _FEE_SCHEDULE[tier]


def get_full_fee_schedule() -> list[FeeRateRange]:
    """全ティアの手数料率レンジ一覧を返す (LOWER → MIDDLE → UPPER の順)。"""
    return [_LOWER, _MIDDLE, _UPPER]
