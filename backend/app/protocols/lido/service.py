# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance サービス層（ビジネスロジック）。"""

from __future__ import annotations

import logging
from decimal import Decimal

from .client import AbstractLidoClient
from .config import LidoConfig
from .schemas import LidoAprResponse, LidoStakeRequest, LidoStakeResponse, LidoStatus

logger = logging.getLogger(__name__)

_WEI_PER_ETH = Decimal("1000000000000000000")


class LidoService:
    """Lido ステーキングのビジネスロジック。"""

    def __init__(self, client: AbstractLidoClient, config: LidoConfig) -> None:
        self._client = client
        self._config = config

    async def stake(self, request: LidoStakeRequest) -> LidoStakeResponse:
        """ETH → stETH ステーキング実行。"""
        # 1. peg 乖離チェック
        ratio = await self._client.get_steth_eth_ratio()
        deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")
        if deviation_pct > Decimal("2"):
            error_msg = (
                f"stETH/ETH peg deviation {deviation_pct}% exceeds "
                f"critical threshold (2%). Staking blocked."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        elif deviation_pct > Decimal(str(self._config.peg_deviation_warn_pct)):
            logger.warning(
                "stETH/ETH ペグ乖離警告: deviation=%.2f%% (閾値=%.2f%%)",
                float(deviation_pct),
                self._config.peg_deviation_warn_pct,
            )

        # 2. APR 取得
        staking_apr = await self._client.get_staking_apr()

        # 3. dry_run の場合はシミュレーションのみ
        if request.dry_run:
            logger.info(
                "LidoService.stake dry_run: amount_eth=%s, apr=%s%%",
                request.amount_eth,
                staking_apr,
            )
            return LidoStakeResponse(
                operation="STAKE",
                amount_eth=request.amount_eth,
                received_steth=request.amount_eth,  # 1:1 simulation
                tx_hash=None,
                staking_apr=staking_apr,
                dry_run=True,
            )

        # 4. 実行
        amount_wei = int(request.amount_eth * _WEI_PER_ETH)
        result = await self._client.stake_eth(amount_wei)

        if not result.success:
            logger.error("stake_eth 失敗: error=%s", result.error)
            raise RuntimeError(f"Lido ステーキング失敗: {result.error}")

        received_steth = Decimal(result.received_steth_wei) / _WEI_PER_ETH
        logger.info(
            "stake 成功: amount_eth=%s, received_steth=%s, tx=%s",
            request.amount_eth,
            received_steth,
            result.tx_hash,
        )
        return LidoStakeResponse(
            operation="STAKE",
            amount_eth=request.amount_eth,
            received_steth=received_steth,
            tx_hash=result.tx_hash,
            staking_apr=staking_apr,
            dry_run=False,
        )

    async def get_status(self) -> LidoStatus:
        """Lido ステータス取得。"""
        wallet_address = self._config.wallet_address or "0x0000000000000000000000000000000000000000"

        steth_balance = await self._client.get_steth_balance(wallet_address)
        staking_apr = await self._client.get_staking_apr()
        ratio = await self._client.get_steth_eth_ratio()
        peg_deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")

        return LidoStatus(
            steth_balance=steth_balance,
            staking_apr=staking_apr,
            steth_eth_ratio=ratio,
            peg_deviation_pct=peg_deviation_pct,
            chain=self._config.chain,
            sandbox=self._config.sandbox,
        )

    async def get_apr(self) -> LidoAprResponse:
        """現在の APR を返す。"""
        apr = await self._client.get_staking_apr()
        return LidoAprResponse(
            staking_apr=apr,
            source="lido_onchain" if not self._config.sandbox else "dummy",
        )
