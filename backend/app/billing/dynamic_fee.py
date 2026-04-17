# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/dynamic_fee.py
"""
動的手数料計算モジュール。

二層戦略:
  GENERAL: 手数料率 3〜15%（一般層、市場状況別）
  UPPER:   手数料率 10〜25%（アッパー層、市場状況別）

市場状況（MarketCondition）× ティアで手数料率レンジを決定する。
純利益（expected_profit − fixed_cost）がゼロ以下の場合はトレードしない（should_trade=False）。

旧ENBベース関数 calculate_dynamic_fee() も後方互換のため保持。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum

logger = logging.getLogger(__name__)

# ティア別手数料率レンジ（旧ENBベース — 後方互換）
_TIER_FEE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "GENERAL": (Decimal("0.03"), Decimal("0.10")),
    "UPPER": (Decimal("0.15"), Decimal("0.25")),
}

_ZERO = Decimal("0")
_ONE = Decimal("1")
_QUANTIZE_RATE = Decimal("0.000001")
_QUANTIZE_USD = Decimal("0.01")

# --- 市場状況別手数料マトリクス ---


class MarketCondition(str, Enum):
    """市場状況分類。"""

    BEAR = "bear"  # 低迷期: APY < 3%
    STABLE = "stable"  # 安定期: 3% ≤ APY ≤ 6%
    BULL = "bull"  # 好調期: APY > 6%


# FEE_MATRIX: (tier, market_condition) → (min_rate, max_rate)
_MARKET_FEE_MATRIX: dict[tuple[str, MarketCondition], tuple[Decimal, Decimal]] = {
    ("GENERAL", MarketCondition.BEAR): (Decimal("0.03"), Decimal("0.05")),
    ("GENERAL", MarketCondition.STABLE): (Decimal("0.06"), Decimal("0.10")),
    ("GENERAL", MarketCondition.BULL): (Decimal("0.08"), Decimal("0.15")),
    ("UPPER", MarketCondition.BEAR): (Decimal("0.10"), Decimal("0.15")),
    ("UPPER", MarketCondition.STABLE): (Decimal("0.15"), Decimal("0.22")),
    ("UPPER", MarketCondition.BULL): (Decimal("0.20"), Decimal("0.25")),
}

# キャップ: 一般層15%, アッパー層25%
_MARKET_FEE_CAPS: dict[str, Decimal] = {
    "GENERAL": Decimal("0.15"),
    "UPPER": Decimal("0.25"),
}

# デフォルト固定経費 ($0.27/トレード = ガス代 + API費用)
_DEFAULT_FIXED_COST_USD = Decimal("0.27")


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


# ---------------------------------------------------------------------------
# 市場状況×ティア別 動的手数料計算 (B-1)
# ---------------------------------------------------------------------------


@dataclass
class MarketFeeResult:
    """市場状況×ティア別手数料計算結果。"""

    fee_rate: Decimal  # 実効手数料率（純利益に対する割合）
    fee_amount: Decimal  # 手数料額（USD, 純利益 × fee_rate）
    should_trade: bool  # 純利益 > 0 かつ経費回収可能
    market_condition: MarketCondition
    tier: str  # "GENERAL" or "UPPER"
    reason: str


def determine_market_condition(current_apy: Decimal) -> MarketCondition:
    """APY から市場状況を判定する。

    Args:
        current_apy: 現在のAPY（%単位, 例: 5.0 → 5%）

    Returns:
        MarketCondition: BEAR(<3%), STABLE(3-6%), BULL(>6%)
    """
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

    原則:
    - 純利益（expected_profit_usd - fixed_cost_usd）≤ 0 → should_trade=False
    - 手数料は純利益に対して課金（ユーザーは絶対にマイナスにならない）
    - 手数料率はFEE_MATRIX[tier][market_condition]のレンジ内でAPY比率により補間

    Args:
        trade_amount_usd: 取引金額（USD）。純利益計算には使用しない。
        tier: "GENERAL" または "UPPER"
        current_apy: 現在のAPY（%単位）
        expected_profit_usd: 1トレードの予想利益（USD）
        fixed_cost_usd: 固定経費（ガス代+API費用, デフォルト$0.27）

    Returns:
        MarketFeeResult

    Raises:
        ValueError: 不明なtierを指定した場合
    """
    if tier not in _MARKET_FEE_CAPS:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {list(_MARKET_FEE_CAPS)}")

    market = determine_market_condition(current_apy)
    net_profit = expected_profit_usd - fixed_cost_usd

    # 純利益 ≤ 0 → トレードしない
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

    # APY比率（0〜1にクランプ、10%を上限として正規化）
    apy_normalized = min(current_apy / Decimal("10"), _ONE)
    fee_rate = min_rate + (max_rate - min_rate) * apy_normalized

    # キャップ適用
    cap = _MARKET_FEE_CAPS[tier]
    fee_rate = min(fee_rate, cap).quantize(_QUANTIZE_RATE, rounding=ROUND_DOWN)

    # 手数料額 = 純利益 × 手数料率
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
