# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/trade_gate.py
"""トレード時点の手数料ゲート計算 (F-13 移行)。

旧 ``app.billing.dynamic_fee`` の market-based 計算を fees/ モジュールに移行。
``MarketCondition`` / ``MarketFeeResult`` / ``calculate_fee_by_market`` を提供する。

月次バッチ計算 (``FeeCalculator``) とは概念的に異なる:
- こちら: per-trade USD ベース、純利益 > 0 ゲートチェック
- FeeCalculator: 月次 JPY ベース、5-step 収益計算

関連:
- app.fees.calculator (月次手数料計算エンジン)
- app.automation.workflow / ai_judgment_scheduler (呼出元)
- docs/45_fee_model_v10_migration_plan.md §4 F-13 行
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_QUANTIZE_RATE = Decimal("0.000001")
_QUANTIZE_USD = Decimal("0.01")

# デフォルト固定経費 ($0.27/トレード = ガス代 + API費用)
_DEFAULT_FIXED_COST_USD = Decimal("0.27")


class MarketCondition(str, Enum):
    """市場状況分類。"""

    BEAR = "bear"
    STABLE = "stable"
    BULL = "bull"


# FEE_MATRIX: (tier, market_condition) → (min_rate, max_rate)
# GENERAL は LOWER alias (DB migration F-16 完了後に削除)
_MARKET_FEE_MATRIX: dict[tuple[str, MarketCondition], tuple[Decimal, Decimal]] = {
    ("LOWER", MarketCondition.BEAR): (Decimal("0.03"), Decimal("0.05")),
    ("LOWER", MarketCondition.STABLE): (Decimal("0.06"), Decimal("0.10")),
    ("LOWER", MarketCondition.BULL): (Decimal("0.08"), Decimal("0.15")),
    ("MIDDLE", MarketCondition.BEAR): (Decimal("0.06"), Decimal("0.10")),
    ("MIDDLE", MarketCondition.STABLE): (Decimal("0.10"), Decimal("0.15")),
    ("MIDDLE", MarketCondition.BULL): (Decimal("0.12"), Decimal("0.18")),
    ("UPPER", MarketCondition.BEAR): (Decimal("0.10"), Decimal("0.15")),
    ("UPPER", MarketCondition.STABLE): (Decimal("0.15"), Decimal("0.22")),
    ("UPPER", MarketCondition.BULL): (Decimal("0.20"), Decimal("0.25")),
    # GENERAL は LOWER と同値 (F-16 DB migration 完了後に削除)
    ("GENERAL", MarketCondition.BEAR): (Decimal("0.03"), Decimal("0.05")),
    ("GENERAL", MarketCondition.STABLE): (Decimal("0.06"), Decimal("0.10")),
    ("GENERAL", MarketCondition.BULL): (Decimal("0.08"), Decimal("0.15")),
}

_MARKET_FEE_CAPS: dict[str, Decimal] = {
    "LOWER": Decimal("0.15"),
    "MIDDLE": Decimal("0.18"),
    "UPPER": Decimal("0.25"),
    "GENERAL": Decimal("0.15"),  # LOWER alias (F-16 完了後に削除)
}


@dataclass
class MarketFeeResult:
    """市場状況×ティア別手数料計算結果。"""

    fee_rate: Decimal
    fee_amount: Decimal
    should_trade: bool
    market_condition: MarketCondition
    tier: str
    reason: str


def determine_market_condition(current_apy: Decimal) -> MarketCondition:
    """APY から市場状況を判定する (BEAR<3%, STABLE 3-6%, BULL>6%)。"""
    if current_apy < Decimal("3"):
        return MarketCondition.BEAR
    if current_apy <= Decimal("6"):
        return MarketCondition.STABLE
    return MarketCondition.BULL


def calculate_fee_by_market(
    trade_amount_usd: Decimal,
    tier: str,
    current_apy: Decimal,
    expected_profit_usd: Decimal,
    fixed_cost_usd: Decimal = _DEFAULT_FIXED_COST_USD,
) -> MarketFeeResult:
    """市場状況×ティア別の動的手数料を計算する。

    純利益 (expected_profit_usd - fixed_cost_usd) ≤ 0 なら should_trade=False。
    手数料は純利益に対して課金 (ユーザーは絶対にマイナスにならない)。
    """
    if tier not in _MARKET_FEE_CAPS:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {list(_MARKET_FEE_CAPS)}")

    market = determine_market_condition(current_apy)
    net_profit = expected_profit_usd - fixed_cost_usd

    if net_profit <= _ZERO:
        logger.info(
            "MarketFee: net_profit=%.4f ≤ 0 → should_trade=False (tier=%s, apy=%s%%)",
            float(net_profit),
            tier,
            float(current_apy),
        )
        return MarketFeeResult(
            fee_rate=_ZERO,
            fee_amount=_ZERO,
            should_trade=False,
            market_condition=market,
            tier=tier,
            reason=f"純利益が負(${net_profit:.4f})のためトレード不推奨",
        )

    min_rate, max_rate = _MARKET_FEE_MATRIX[(tier, market)]
    apy_normalized = min(current_apy / Decimal("10"), _ONE)
    fee_rate = min_rate + (max_rate - min_rate) * apy_normalized
    cap = _MARKET_FEE_CAPS[tier]
    fee_rate = min(fee_rate, cap).quantize(_QUANTIZE_RATE, rounding=ROUND_DOWN)
    fee_amount = (net_profit * fee_rate).quantize(_QUANTIZE_USD, rounding=ROUND_DOWN)

    logger.info(
        "MarketFee[tier=%s, market=%s]: apy=%.2f%%, net_profit=%.4f, "
        "fee_rate=%.4f, fee_amount=%.2f (trade_amount=%.2f)",
        tier,
        market.value,
        float(current_apy),
        float(net_profit),
        float(fee_rate),
        float(fee_amount),
        float(trade_amount_usd),
    )

    return MarketFeeResult(
        fee_rate=fee_rate,
        fee_amount=fee_amount,
        should_trade=True,
        market_condition=market,
        tier=tier,
        reason=f"tier={tier}, market={market.value}, fee_rate={float(fee_rate):.1%}",
    )
