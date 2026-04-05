# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido + Aave V3 複合戦略。
⚠️ backend/app/aave/ のコードは変更しない。既存 AaveService を読み取り専用で参照。
"""

from __future__ import annotations

import logging
from decimal import Decimal

from .client import AbstractLidoClient
from .config import LidoConfig
from .schemas import CompoundYieldEstimate, LidoStakeRequest, LidoStakeResponse

logger = logging.getLogger(__name__)

# Aave V3 stETH supply APR の推定値（PoC 用固定値、本番では Aave API から取得）
_AAVE_STETH_SUPPLY_APR_ESTIMATE = Decimal("1.5")


class LidoAaveStrategy:
    """Lido + Aave V3 複合戦略（ETH → stETH → Aave supply）。"""

    def __init__(self, lido_client: AbstractLidoClient, config: LidoConfig) -> None:
        self._lido_client = lido_client
        self._config = config

    async def execute_yield_strategy(
        self,
        amount_eth: Decimal,
        dry_run: bool = True,
    ) -> LidoStakeResponse:
        """
        複合戦略実行:
        1. ETH → stETH（Lido）
        2. stETH → Aave V3 supply（担保として供給）★PoC段階はシミュレーション

        PoC フェーズでは Aave supply はログのみ（実際の送信は行わない）。
        """
        from .service import LidoService

        lido_service = LidoService(client=self._lido_client, config=self._config)
        stake_request = LidoStakeRequest(amount_eth=amount_eth, dry_run=dry_run)
        stake_result = await lido_service.stake(stake_request)

        if not dry_run and stake_result.tx_hash:
            # TODO: Phase 2 本実装で Aave supply を追加
            # PoC では stETH 取得後のログのみ
            logger.info(
                "LidoAaveStrategy: stETH=%s を Aave V3 supply にシミュレーション（PoC）",
                stake_result.received_steth,
            )

        return stake_result

    async def estimate_compound_yield(self, amount_eth: Decimal) -> CompoundYieldEstimate:
        """複合利回りの推定値を返す。

        複合 APR = Lido staking APR + Aave stETH supply APR
        例: 3.5% + 1.5% = 5.0%
        """
        lido_apr = await self._lido_client.get_staking_apr()
        aave_apr = _AAVE_STETH_SUPPLY_APR_ESTIMATE
        compound_apr = lido_apr + aave_apr
        estimated_annual_yield = amount_eth * compound_apr / Decimal("100")

        logger.info(
            "複合利回り推定: lido=%.2f%%, aave=%.2f%%, compound=%.2f%%, amount=%s ETH, yield=%s ETH",
            float(lido_apr),
            float(aave_apr),
            float(compound_apr),
            amount_eth,
            estimated_annual_yield,
        )

        return CompoundYieldEstimate(
            lido_staking_apr=lido_apr,
            aave_supply_apr=aave_apr,
            compound_apr=compound_apr,
            amount_eth=amount_eth,
            estimated_annual_yield_eth=estimated_annual_yield,
        )
