# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/slippage_guard.py
"""Slippage protection for Aave operations."""

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# ステーブルコインとみなすアセットシンボル（大文字）
_STABLECOIN_SYMBOLS = frozenset({"USDC", "USDT", "DAI", "BUSD", "TUSD", "FRAX"})


class SlippageGuard:
    """操作前後の価格変動を検知して保護する。

    Usage:
        guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
        guard.record_pre_price("USDC", Decimal("1.00"))
        # ... approve tx ...
        ok = guard.check_post_price("USDC", Decimal("0.99"))  # True (1% < 2%)
    """

    def __init__(self, max_deviation_pct: Decimal = Decimal("2.0")) -> None:
        self.max_deviation_pct = max_deviation_pct
        self._pre_operation_prices: dict[str, Decimal] = {}

    def record_pre_price(self, asset: str, price_usd: Decimal) -> None:
        """操作前の価格を記録する。"""
        self._pre_operation_prices[asset] = price_usd
        logger.debug("SlippageGuard: recorded %s price = %s", asset, price_usd)

    def check_post_price(self, asset: str, current_price_usd: Decimal) -> bool:
        """操作後の価格が許容範囲内か確認する。

        Returns:
            True: 許容範囲内（操作を続行してよい）
            False: 逸脱超過（操作を中止すべき）
        """
        pre_price = self._pre_operation_prices.get(asset)
        if pre_price is None or pre_price == Decimal("0"):
            logger.warning("SlippageGuard: no pre-price for %s, allowing", asset)
            return True

        deviation = abs(current_price_usd - pre_price) / pre_price * Decimal("100")
        if deviation > self.max_deviation_pct:
            logger.warning(
                "SlippageGuard: %s price deviation %.4f%% exceeds max %.2f%%",
                asset,
                deviation,
                self.max_deviation_pct,
            )
            return False
        return True

    def is_stablecoin(self, asset: str) -> bool:
        """ステーブルコインかどうかを返す（大文字小文字を区別しない）。"""
        return asset.upper() in _STABLECOIN_SYMBOLS

    def clear(self, asset: Optional[str] = None) -> None:
        """記録した pre-price をクリアする。"""
        if asset:
            self._pre_operation_prices.pop(asset, None)
        else:
            self._pre_operation_prices.clear()
