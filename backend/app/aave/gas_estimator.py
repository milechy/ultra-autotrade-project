# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/gas_estimator.py
"""
動的ガス見積もりユーティリティ。

- estimate_gas_with_buffer: web3のestimate_gasに20%バッファを加算
- estimate_gas_cost_usd: ガスコストをUSD換算
- is_gas_cost_acceptable: MAX_GAS_COST_USD上限チェック
- is_profitable: ガスコスト < 期待収益チェック
- ETH/USD価格取得失敗時は保守的固定値（ETH_USD_FALLBACK_PRICE）を使用
- estimate_gas失敗時はフォールバック固定値（fallback_gas）を使用
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# ETH/USD フォールバック価格（API失敗時に使用。ENV: ETH_USD_FALLBACK_PRICE）
# デフォルトは現実値付近の $2100。実勢価格が大きく乖離した場合は env を更新する。
ETH_USD_FALLBACK_PRICE = Decimal(os.environ.get("ETH_USD_FALLBACK_PRICE", "2100.00"))

# デフォルトフォールバックガス値（estimate_gas失敗時）
DEFAULT_FALLBACK_GAS_APPROVE = 100000
DEFAULT_FALLBACK_GAS_SUPPLY = 300000
DEFAULT_FALLBACK_GAS_WITHDRAW = 300000

# フォールバックガス価格（wei単位、提案生成時など web3 なしの概算用。ENV: ETH_GAS_PRICE_GWEI_FALLBACK）
DEFAULT_GAS_PRICE_WEI = Decimal(os.environ.get("ETH_GAS_PRICE_GWEI_FALLBACK", "30")) * Decimal(
    "1000000000"
)  # デフォルト 30 gwei


def estimate_static_gas_cost_usd(
    operation: str,
    eth_usd_price: Decimal | None = None,
    gas_price_wei: Decimal | None = None,
) -> Decimal:
    """Web3接続なしのフォールバックガス代見積もり（提案生成時用）。

    実際のガス価格は実行時に変わるため、これはあくまで表示用概算値。
    """
    gas_units = (
        DEFAULT_FALLBACK_GAS_WITHDRAW
        if operation.upper() == "WITHDRAW"
        else DEFAULT_FALLBACK_GAS_SUPPLY
    )
    price = eth_usd_price if eth_usd_price is not None else ETH_USD_FALLBACK_PRICE
    g_price = gas_price_wei if gas_price_wei is not None else DEFAULT_GAS_PRICE_WEI
    gas_cost_eth = Decimal(str(gas_units)) * g_price / Decimal("1000000000000000000")
    cost_usd = gas_cost_eth * price
    logger.debug(
        "静的ガス概算(%s): %d units × %s wei = $%s USD",
        operation,
        gas_units,
        g_price,
        cost_usd,
    )
    return cost_usd


class GasEstimator:
    """動的ガス見積もり + 上限キャップ"""

    # ガス代上限（USD相当）— これ以上のガス代は拒否
    MAX_GAS_COST_USD = Decimal("50.00")

    # 見積もりに対するバッファ倍率（20%余裕）
    GAS_BUFFER_MULTIPLIER = Decimal("1.20")

    def __init__(self, w3: Any) -> None:
        self.w3 = w3

    def estimate_gas_with_buffer(self, tx_params: dict[str, Any], fallback_gas: int) -> int:
        """
        ガス見積もり + 20%バッファ。
        estimate_gas失敗時はfallback_gasを返す。
        """
        try:
            estimated = self.w3.eth.estimate_gas(tx_params)
            result = int(Decimal(str(estimated)) * self.GAS_BUFFER_MULTIPLIER)
            logger.debug("estimate_gas: %d → %d (with buffer)", estimated, result)
            return result
        except Exception as exc:
            logger.warning("estimate_gas 失敗 → フォールバック値 %d を使用: %s", fallback_gas, exc)
            return fallback_gas

    def get_gas_price(self) -> int:
        """現在のガス価格を取得（wei単位）。"""
        return int(self.w3.eth.gas_price)

    def estimate_gas_cost_usd(
        self, gas_units: int, eth_usd_price: Decimal | None = None
    ) -> Decimal:
        """
        ガスコストをUSD換算。
        eth_usd_price が None の場合はフォールバック価格を使用。
        Financial calculations: Decimal ONLY（float禁止）
        """
        gas_price_wei = Decimal(str(self.get_gas_price()))
        gas_cost_wei = Decimal(str(gas_units)) * gas_price_wei
        gas_cost_eth = gas_cost_wei / Decimal("1000000000000000000")  # 1e18

        price = eth_usd_price if eth_usd_price is not None else ETH_USD_FALLBACK_PRICE
        cost_usd = gas_cost_eth * price
        logger.debug(
            "ガスコスト: %d units × %s wei/gas = %s ETH = $%s USD",
            gas_units,
            gas_price_wei,
            gas_cost_eth,
            cost_usd,
        )
        return cost_usd

    def is_gas_cost_acceptable(self, gas_units: int, eth_usd_price: Decimal | None = None) -> bool:
        """
        ガスコストが MAX_GAS_COST_USD 以下かチェック。
        True = 許容範囲内（実行OK）
        False = 上限超過（実行拒否）
        """
        cost_usd = self.estimate_gas_cost_usd(gas_units, eth_usd_price)
        acceptable = cost_usd <= self.MAX_GAS_COST_USD
        if not acceptable:
            logger.warning(
                "ガスコスト $%s が上限 $%s を超過 — tx を拒否",
                cost_usd,
                self.MAX_GAS_COST_USD,
            )
        return acceptable

    def is_profitable(self, gas_cost_usd: Decimal, expected_benefit_usd: Decimal) -> bool:
        """ガスコスト < 期待収益 かチェック（07_aave_operation_logic.md）"""
        return expected_benefit_usd > gas_cost_usd
