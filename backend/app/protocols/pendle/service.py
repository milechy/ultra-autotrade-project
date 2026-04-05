# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance サービス層（ビジネスロジック）。"""

from __future__ import annotations

import logging
from decimal import Decimal

from .client import AbstractPendleClient
from .config import PendleConfig
from .schemas import (
    PendleMarketInfo,
    PendleMintRequest,
    PendleMintResponse,
    PendleRedeemRequest,
    PendleRedeemResponse,
)

logger = logging.getLogger(__name__)


class PendleService:
    """Pendle Finance のビジネスロジック。"""

    def __init__(self, client: AbstractPendleClient, config: PendleConfig) -> None:
        self._client = client
        self._config = config

    async def mint(self, request: PendleMintRequest) -> PendleMintResponse:
        """PT または YT のミント実行。"""
        # 1. マーケット情報取得
        market_info = await self._client.get_market_info(request.market_address)

        # 2. 満期チェック（config.min_days_to_maturity 未満の場合は拒否）
        if market_info.days_to_maturity < self._config.min_days_to_maturity:
            raise ValueError(
                f"満期まで {market_info.days_to_maturity} 日しかありません。"
                f"最低 {self._config.min_days_to_maturity} 日必要です。"
            )

        # 3. implied APY 警告チェック
        if market_info.implied_apy > self._config.max_implied_apy_pct:
            logger.warning(
                "implied APY 警告: %.2f%% > 閾値 %.2f%%（異常値の可能性）",
                float(market_info.implied_apy),
                float(self._config.max_implied_apy_pct),
            )

        pt_price = market_info.pt_price
        yt_price = market_info.yt_price
        days = market_info.days_to_maturity

        # 4. 固定利回り計算
        implied_fixed_yield = (
            (Decimal("1") - pt_price)
            / pt_price
            * (Decimal("365") / Decimal(str(days)))
            * Decimal("100")
        )

        # 5. dry_run の場合はシミュレーションのみ
        if request.dry_run:
            if request.strategy == "pt_fixed":
                pt_received = request.amount / pt_price
                logger.info(
                    "PendleService.mint dry_run (pt_fixed): amount=%s, pt_received=%s, yield=%.4f%%",
                    request.amount,
                    pt_received,
                    float(implied_fixed_yield),
                )
                return PendleMintResponse(
                    operation="MINT_PT",
                    input_amount=request.amount,
                    pt_received=pt_received,
                    yt_received=None,
                    implied_fixed_yield=implied_fixed_yield,
                    maturity=market_info.maturity,
                    tx_hash=None,
                    dry_run=True,
                )
            else:  # yt_leverage
                yt_received = request.amount / yt_price
                logger.info(
                    "PendleService.mint dry_run (yt_leverage): amount=%s, yt_received=%s",
                    request.amount,
                    yt_received,
                )
                return PendleMintResponse(
                    operation="MINT_YT",
                    input_amount=request.amount,
                    pt_received=None,
                    yt_received=yt_received,
                    implied_fixed_yield=implied_fixed_yield,
                    maturity=market_info.maturity,
                    tx_hash=None,
                    dry_run=True,
                )

        # 6. 実行（SY ラップ → PT/YT 分割）
        sy_result = await self._client.mint_sy(request.asset, request.amount)
        if not sy_result.get("success"):
            raise RuntimeError("SY ミント失敗")

        sy_amount: Decimal = sy_result["sy_received"]
        split_result = await self._client.mint_pt_yt(sy_amount, request.market_address)
        if not split_result.get("success"):
            raise RuntimeError("PT/YT 分割失敗")

        if request.strategy == "pt_fixed":
            pt_received = split_result["pt_received"]
            logger.info(
                "mint 成功 (pt_fixed): amount=%s, pt_received=%s, tx=%s",
                request.amount,
                pt_received,
                split_result["tx_hash"],
            )
            return PendleMintResponse(
                operation="MINT_PT",
                input_amount=request.amount,
                pt_received=pt_received,
                yt_received=None,
                implied_fixed_yield=implied_fixed_yield,
                maturity=market_info.maturity,
                tx_hash=split_result["tx_hash"],
                dry_run=False,
            )
        else:  # yt_leverage
            yt_received = split_result["yt_received"]
            logger.info(
                "mint 成功 (yt_leverage): amount=%s, yt_received=%s, tx=%s",
                request.amount,
                yt_received,
                split_result["tx_hash"],
            )
            return PendleMintResponse(
                operation="MINT_YT",
                input_amount=request.amount,
                pt_received=None,
                yt_received=yt_received,
                implied_fixed_yield=implied_fixed_yield,
                maturity=market_info.maturity,
                tx_hash=split_result["tx_hash"],
                dry_run=False,
            )

    async def redeem(self, request: PendleRedeemRequest) -> PendleRedeemResponse:
        """PT または YT のリデーム実行。"""
        # 満期チェック（PT の場合のみ）
        if request.token_type == "PT":  # noqa: S105
            market_info = await self._client.get_market_info(request.market_address)
            if market_info.days_to_maturity > 0:
                raise ValueError(
                    f"Cannot redeem PT before maturity. "
                    f"Days remaining: {market_info.days_to_maturity}. "
                    f"Use market sell instead."
                )

        if request.dry_run:
            logger.info(
                "PendleService.redeem dry_run: token_type=%s, amount=%s",
                request.token_type,
                request.amount,
            )
            # dry_run シミュレーション
            if request.token_type == "PT":  # noqa: S105
                return PendleRedeemResponse(
                    operation="REDEEM_PT",
                    redeemed_amount=request.amount,
                    underlying_received=request.amount,  # 満期時 1:1
                    tx_hash=None,
                    dry_run=True,
                )
            else:  # YT
                market_info = await self._client.get_market_info(request.market_address)
                underlying = request.amount * market_info.yt_price
                return PendleRedeemResponse(
                    operation="REDEEM_YT",
                    redeemed_amount=request.amount,
                    underlying_received=underlying,
                    tx_hash=None,
                    dry_run=True,
                )

        # 実行
        if request.token_type == "PT":  # noqa: S105
            result = await self._client.redeem_pt(request.amount, request.market_address)
            operation = "REDEEM_PT"
        else:
            result = await self._client.redeem_yt(request.amount, request.market_address)
            operation = "REDEEM_YT"

        if not result.get("success"):
            raise RuntimeError(f"{operation} 失敗")

        underlying_received: Decimal = result["underlying_received"]
        logger.info(
            "redeem 成功: operation=%s, amount=%s, underlying=%s, tx=%s",
            operation,
            request.amount,
            underlying_received,
            result["tx_hash"],
        )
        return PendleRedeemResponse(
            operation=operation,
            redeemed_amount=request.amount,
            underlying_received=underlying_received,
            tx_hash=result["tx_hash"],
            dry_run=False,
        )

    async def get_market_info(self, market_address: str) -> PendleMarketInfo:
        """マーケット情報を取得する。"""
        return await self._client.get_market_info(market_address)

    async def estimate_fixed_yield(self, amount: Decimal, market_address: str) -> Decimal:
        """固定利回りの年換算推定値を返す（%）。

        計算式: (1 - pt_price) / pt_price * (365 / days_to_maturity) * 100
        """
        market_info = await self._client.get_market_info(market_address)
        pt_price = market_info.pt_price
        days = market_info.days_to_maturity

        if days <= 0:
            return Decimal("0")

        annualized_yield = (
            (Decimal("1") - pt_price)
            / pt_price
            * (Decimal("365") / Decimal(str(days)))
            * Decimal("100")
        )
        logger.info(
            "estimate_fixed_yield: amount=%s, pt_price=%s, days=%d, yield=%.4f%%",
            amount,
            pt_price,
            days,
            float(annualized_yield),
        )
        return annualized_yield
