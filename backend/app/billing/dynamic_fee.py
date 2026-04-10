# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/dynamic_fee.py
"""
ENBベース動的手数料計算モジュール。

二層戦略:
  GENERAL: 手数料率 3〜10%（一般層）
  UPPER:   手数料率 15〜25%（アッパー層）

ENB（Expected Net Benefit）がゼロ以下の場合はトレードしない（should_trade=False）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

logger = logging.getLogger(__name__)

# ティア別手数料率レンジ
_TIER_FEE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "GENERAL": (Decimal("0.03"), Decimal("0.10")),
    "UPPER": (Decimal("0.15"), Decimal("0.25")),
}

_ZERO = Decimal("0")
_ONE = Decimal("1")
_QUANTIZE_RATE = Decimal("0.000001")
_QUANTIZE_USD = Decimal("0.01")


@dataclass
class DynamicFeeResult:
    """動的手数料計算結果。"""

    fee_rate: Decimal  # 実効手数料率（0.03〜0.25）
    fee_amount: Decimal  # 手数料額（USD）
    net_trade_amount: Decimal  # 実効取引額（trade_amount - fee_amount）
    should_trade: bool  # ENB > 0 かどうか（False ならトレードしない）
    tier: str  # "GENERAL" or "UPPER"


def calculate_dynamic_fee(
    enb: Decimal,
    tier: str,
    trade_amount_usd: Decimal,
) -> DynamicFeeResult:
    """
    ENBベースの動的手数料を計算する。

    ロジック:
    1. ENB ≤ 0 → fee_rate = 0, should_trade = False（トレードしない）
    2. enb_ratio = min(enb / trade_amount_usd, 1.0)
    3. GENERAL: fee_rate = 0.03 + enb_ratio * (0.10 - 0.03)
       UPPER:   fee_rate = 0.15 + enb_ratio * (0.25 - 0.15)
    4. fee_amount = trade_amount_usd * fee_rate
    5. net_trade_amount = trade_amount_usd - fee_amount

    Args:
        enb: Expected Net Benefit（AI Optimizerから受け取る値、USD単位）
        tier: "GENERAL" または "UPPER"
        trade_amount_usd: 取引金額（USD）

    Returns:
        DynamicFeeResult

    Raises:
        ValueError: 不明なtierを指定した場合
    """
    if tier not in _TIER_FEE_RANGES:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {list(_TIER_FEE_RANGES)}")

    # ENB ≤ 0 → トレードしない
    if enb <= _ZERO:
        logger.info(
            "ENB=%.4f ≤ 0: should_trade=False, skipping fee calculation (tier=%s)",
            float(enb),
            tier,
        )
        return DynamicFeeResult(
            fee_rate=_ZERO,
            fee_amount=_ZERO,
            net_trade_amount=trade_amount_usd,
            should_trade=False,
            tier=tier,
        )

    base_rate, max_rate = _TIER_FEE_RANGES[tier]

    # ENB比率（0〜1にクランプ）
    if trade_amount_usd > _ZERO:
        enb_ratio = min(enb / trade_amount_usd, _ONE)
    else:
        enb_ratio = _ZERO

    # 手数料率計算
    fee_rate = base_rate + enb_ratio * (max_rate - base_rate)
    fee_rate = fee_rate.quantize(_QUANTIZE_RATE, rounding=ROUND_DOWN)

    # 手数料額・実効取引額計算
    fee_amount = (trade_amount_usd * fee_rate).quantize(_QUANTIZE_USD, rounding=ROUND_DOWN)
    net_trade_amount = trade_amount_usd - fee_amount

    logger.info(
        "DynamicFee[tier=%s]: enb=%.4f, ratio=%.4f, fee_rate=%.4f, fee_amount=%.2f, net=%.2f",
        tier,
        float(enb),
        float(enb_ratio),
        float(fee_rate),
        float(fee_amount),
        float(net_trade_amount),
    )

    return DynamicFeeResult(
        fee_rate=fee_rate,
        fee_amount=fee_amount,
        net_trade_amount=net_trade_amount,
        should_trade=True,
        tier=tier,
    )
