# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/trade_gate.py
"""トレードゲート: §4 の「予想利益 > 経費」判定のみを行う。

手数料モデル v10 確定仕様書 §4 に基づく設計:
    1TX予想利益 = デポジット × APY ÷ 365
    1TX経費    = 実ガス代 + 実API代
    予想利益 > 経費 → should_trade=True（トレード実行）
    予想利益 ≤ 経費 → should_trade=False（トレードしない）

手数料（30/25/20%）は月次バッチ（F-7）で計算する。
per-trade の fee_rate / fee_amount は常に 0 を返す。

関連:
- app.fees.calculator (月次手数料計算エンジン、F-5)
- app.automation.workflow / ai_judgment_scheduler (呼出元)
- docs/45_fee_model_v10_migration_plan.md §4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_QUANTIZE_USD = Decimal("0.01")

# デフォルト固定経費 ($0.27/トレード = ガス代 + API費用)
_DEFAULT_FIXED_COST_USD = Decimal("0.27")


@dataclass
class MarketFeeResult:
    """トレードゲート判定結果。

    fee_rate / fee_amount は月次バッチ（F-7）が計算するため常に 0。
    """

    should_trade: bool
    reason: str
    fee_rate: Decimal = _ZERO
    fee_amount: Decimal = _ZERO
    tier: str = ""


def calculate_fee_by_market(
    trade_amount_usd: Decimal,
    tier: str,
    current_apy: Decimal,
    expected_profit_usd: Decimal,
    fixed_cost_usd: Decimal = _DEFAULT_FIXED_COST_USD,
) -> MarketFeeResult:
    """§4 トレードゲート: 純利益（予想利益 − 経費）> 0 なら実行。

    手数料（30/25/20% tier 別）は月次バッチ（F-7）で計算する。
    per-trade では fee_rate=0 / fee_amount=0 を返す。

    Args:
        trade_amount_usd: 取引額 (USD)。ログ用。
        tier: ユーザー tier 文字列 (LOWER/MIDDLE/UPPER/GENERAL)。ログ用。
        current_apy: 現在の Aave supply APY (%)。ログ用。
        expected_profit_usd: 期待収益 (USD)。
        fixed_cost_usd: 固定経費 (USD、デフォルト $0.27)。

    Returns:
        MarketFeeResult: should_trade フラグと理由。fee_rate/fee_amount は常に 0。
    """
    net_profit = (expected_profit_usd - fixed_cost_usd).quantize(_QUANTIZE_USD, rounding=ROUND_DOWN)

    if net_profit <= _ZERO:
        logger.info(
            "TradeGate: should_trade=False — net_profit=%.4f ≤ 0 (tier=%s, apy=%.2f%%,"
            " trade=%.2f, expected=%.4f, cost=%.4f)",
            float(net_profit),
            tier,
            float(current_apy),
            float(trade_amount_usd),
            float(expected_profit_usd),
            float(fixed_cost_usd),
        )
        return MarketFeeResult(
            should_trade=False,
            reason=f"純利益が負(${net_profit:.4f})のためトレード不推奨",
            tier=tier,
        )

    logger.info(
        "TradeGate: should_trade=True — net_profit=%.4f (tier=%s, apy=%.2f%%,"
        " trade=%.2f) — fee は月次バッチで計算",
        float(net_profit),
        tier,
        float(current_apy),
        float(trade_amount_usd),
    )
    return MarketFeeResult(
        should_trade=True,
        reason="ゲート通過 (fee は月次バッチで計算)",
        tier=tier,
    )
