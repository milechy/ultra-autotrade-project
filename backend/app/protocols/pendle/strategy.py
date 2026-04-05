# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance 戦略層（複合戦略・戦略評価）。"""

from __future__ import annotations

import logging
from decimal import Decimal

from ..lido.client import AbstractLidoClient
from ..lido.schemas import LidoStakeRequest
from .client import AbstractPendleClient
from .schemas import (
    CompoundResult,
    PendleMarketInfo,
    StrategyComparison,
    StrategyEvaluation,
)

logger = logging.getLogger(__name__)

# Aave V3 stETH supply APR の推定値（PoC 用固定値、本番では Aave API から取得）
_AAVE_STETH_SUPPLY_APR_ESTIMATE = Decimal("1.5")


class PendleFixedYieldStrategy:
    """Pendle PT 固定利回り戦略（低リスク）。

    PT をディスカウントで購入し、満期時に 1:1 でリデームすることで
    固定利回りを確定する。Aave supply APR より高い場合に推奨。
    """

    async def evaluate(
        self,
        market_info: PendleMarketInfo,
        aave_apr: Decimal,
    ) -> StrategyEvaluation:
        """戦略を評価して StrategyEvaluation を返す。

        固定利回り = (1 - pt_price) / pt_price * (365 / days_to_maturity) * 100
        Aave APR より高い場合に推奨。
        """
        pt_price = market_info.pt_price
        days = market_info.days_to_maturity

        if days <= 0 or pt_price <= Decimal("0"):
            return StrategyEvaluation(
                strategy="pt_fixed",
                recommended=False,
                expected_apy=Decimal("0"),
                risk_level="low",
                details="満期日が無効です",
            )

        fixed_yield_pct = (
            (Decimal("1") - pt_price)
            / pt_price
            * (Decimal("365") / Decimal(str(days)))
            * Decimal("100")
        )

        recommended = fixed_yield_pct > aave_apr
        details = (
            f"PT 固定利回り {fixed_yield_pct:.4f}% vs Aave APR {aave_apr:.2f}%。"
            f"{'推奨: 固定利回りが Aave を上回ります。' if recommended else '非推奨: Aave の方が有利です。'}"
        )

        logger.info(
            "PendleFixedYieldStrategy: fixed_yield=%.4f%%, aave_apr=%.2f%%, recommended=%s",
            float(fixed_yield_pct),  # float OK
            float(aave_apr),  # float OK
            recommended,
        )

        return StrategyEvaluation(
            strategy="pt_fixed",
            recommended=recommended,
            expected_apy=fixed_yield_pct,
            risk_level="low",
            details=details,
        )


class PendleYieldLeverageStrategy:
    """Pendle YT 利回りレバレッジ戦略（高リスク）。

    YT を購入することで、staking APR に対してレバレッジをかける。
    current_staking_apr > ブレークイーブン利回りの場合のみ利益が出る。
    """

    async def evaluate(
        self,
        market_info: PendleMarketInfo,
        current_staking_apr: Decimal,
    ) -> StrategyEvaluation:
        """戦略を評価して StrategyEvaluation を返す。

        ブレークイーブン利回り = yt_price * (365 / days_to_maturity) * 100
        current_staking_apr > ブレークイーブン の場合に利益。
        ただし高リスクのためアグレッシブモードのみ推奨。
        """
        yt_price = market_info.yt_price
        days = market_info.days_to_maturity

        if days <= 0 or yt_price <= Decimal("0"):
            return StrategyEvaluation(
                strategy="yt_leverage",
                recommended=False,
                expected_apy=Decimal("0"),
                risk_level="high",
                details="満期日が無効です",
            )

        breakeven_pct = yt_price * (Decimal("365") / Decimal(str(days))) * Decimal("100")
        is_profitable = current_staking_apr > breakeven_pct

        # YT 購入による期待 APY = (current_staking_apr - breakeven) / yt_price * 100
        if yt_price > Decimal("0"):
            expected_apy = (current_staking_apr - breakeven_pct) / yt_price
        else:
            expected_apy = Decimal("0")

        # 高リスク戦略のため、利益が出る場合でも recommended=False（アグレッシブモードのみ）
        recommended = False
        details = (
            f"ブレークイーブン: {breakeven_pct:.4f}%、"
            f"現在 staking APR: {current_staking_apr:.2f}%。"
            f"{'利益見込みあり（高リスク）。アグレッシブモードのみ推奨。' if is_profitable else '現在のステーキング利回りではブレークイーブンに届きません。'}"
        )

        logger.info(
            "PendleYieldLeverageStrategy: breakeven=%.4f%%, staking_apr=%.2f%%, profitable=%s",
            float(breakeven_pct),  # float OK
            float(current_staking_apr),  # float OK
            is_profitable,
        )

        return StrategyEvaluation(
            strategy="yt_leverage",
            recommended=recommended,
            expected_apy=expected_apy,
            risk_level="high",
            details=details,
        )


class LidoPendleCompoundStrategy:
    """Lido + Pendle 複合戦略（ETH → stETH → PT/YT）。

    Step 1: ETH → stETH（Lido）
    Step 2: stETH → SY-stETH → PT or YT（Pendle）
    """

    def __init__(
        self,
        lido_client: AbstractLidoClient,
        pendle_client: AbstractPendleClient,
    ) -> None:
        self._lido_client = lido_client
        self._pendle_client = pendle_client

    async def execute(
        self,
        amount_eth: Decimal,
        strategy: str,
        dry_run: bool = True,
    ) -> CompoundResult:
        """複合戦略を実行する。

        strategy: 'pt_fixed' または 'yt_leverage'
        """
        steps: list[str] = []

        # Step 1: ETH → stETH（Lido）
        from ..lido.service import LidoService  # noqa: PLC0415
        from .config import PendleConfig  # noqa: PLC0415

        lido_config_obj = None
        try:
            from ..lido.config import get_lido_config  # noqa: PLC0415

            lido_config_obj = get_lido_config()
        except Exception:  # noqa: S110
            pass

        if lido_config_obj is not None:
            lido_service = LidoService(client=self._lido_client, config=lido_config_obj)
        else:
            # フォールバック：直接クライアントを使用
            lido_service = None

        if dry_run:
            staking_apr = await self._lido_client.get_staking_apr()
            steps.append(
                f"[シミュレーション] Step 1: {amount_eth} ETH → stETH（Lido、APR {staking_apr:.2f}%）"
            )
            steth_amount = amount_eth  # 1:1 simulation
        else:
            if lido_service is not None:
                stake_req = LidoStakeRequest(amount_eth=amount_eth, dry_run=False)
                stake_result = await lido_service.stake(stake_req)
                steth_amount = stake_result.received_steth
                steps.append(
                    f"Step 1: {amount_eth} ETH → {steth_amount} stETH（Lido、tx={stake_result.tx_hash}）"
                )
            else:
                steth_amount = amount_eth
                steps.append(f"Step 1: {amount_eth} ETH → stETH（Lido、シミュレーション）")

        # Step 2: stETH → SY → PT or YT（Pendle）
        pendle_config = PendleConfig()
        market_address = pendle_config.market_address

        market_info = await self._pendle_client.get_market_info(market_address)

        if strategy == "pt_fixed":
            pt_price = market_info.pt_price
            pt_amount = steth_amount / pt_price
            days = market_info.days_to_maturity
            fixed_yield_pct = (
                (Decimal("1") - pt_price)
                / pt_price
                * (Decimal("365") / Decimal(str(days)))
                * Decimal("100")
            )
            if dry_run:
                steps.append(
                    f"[シミュレーション] Step 2: {steth_amount} stETH → {pt_amount:.6f} PT"
                    f"（固定利回り {fixed_yield_pct:.4f}%、満期 {market_info.days_to_maturity} 日後）"
                )
            else:
                sy_result = await self._pendle_client.mint_sy("stETH", steth_amount)
                split_result = await self._pendle_client.mint_pt_yt(
                    sy_result["sy_received"], market_address
                )
                steps.append(
                    f"Step 2: {steth_amount} stETH → {split_result['pt_received']:.6f} PT"
                    f"（tx={split_result['tx_hash']}）"
                )

            lido_apr = await self._lido_client.get_staking_apr()
            total_apy = lido_apr + fixed_yield_pct
            final_position = (
                f"PT-stETH（{pt_amount:.6f} PT、満期 {market_info.days_to_maturity} 日後）"
            )

        else:  # yt_leverage
            yt_price = market_info.yt_price
            yt_amount = steth_amount / yt_price
            if dry_run:
                steps.append(
                    f"[シミュレーション] Step 2: {steth_amount} stETH → {yt_amount:.6f} YT"
                    f"（利回りレバレッジ、満期 {market_info.days_to_maturity} 日後）"
                )
            else:
                sy_result = await self._pendle_client.mint_sy("stETH", steth_amount)
                split_result = await self._pendle_client.mint_pt_yt(
                    sy_result["sy_received"], market_address
                )
                steps.append(
                    f"Step 2: {steth_amount} stETH → {split_result['yt_received']:.6f} YT"
                    f"（tx={split_result['tx_hash']}）"
                )

            lido_apr = await self._lido_client.get_staking_apr()
            total_apy = lido_apr  # YT の APY は staking APR に依存
            final_position = f"YT-stETH（{yt_amount:.6f} YT）"

        logger.info(
            "LidoPendleCompoundStrategy.execute: strategy=%s, amount=%s, total_apy=%.4f%%, dry_run=%s",
            strategy,
            amount_eth,
            float(total_apy),  # float OK
            dry_run,
        )

        return CompoundResult(
            steps=steps,
            final_position=final_position,
            total_expected_apy=total_apy,
            dry_run=dry_run,
        )

    async def compare_strategies(
        self,
        amount: Decimal,
        market_address: str,
    ) -> StrategyComparison:
        """3つの戦略を比較する。

        1. Aave のみ（APR 1.5%）
        2. Lido + Aave（Lido APR + Aave APR）
        3. Lido + Pendle PT（Lido APR + Pendle 固定利回り）
        """
        market_info = await self._pendle_client.get_market_info(market_address)
        lido_apr = await self._lido_client.get_staking_apr()
        aave_apr = _AAVE_STETH_SUPPLY_APR_ESTIMATE

        # 戦略 1: Aave のみ
        aave_only_apy = aave_apr
        aave_only = StrategyEvaluation(
            strategy="aave_only",
            recommended=False,
            expected_apy=aave_only_apy,
            risk_level="low",
            details=f"Aave V3 stETH supply のみ（推定 APR {aave_apr:.2f}%）",
        )

        # 戦略 2: Lido + Aave
        lido_aave_apy = lido_apr + aave_apr
        lido_aave = StrategyEvaluation(
            strategy="lido_aave",
            recommended=False,
            expected_apy=lido_aave_apy,
            risk_level="low",
            details=(
                f"Lido staking（{lido_apr:.2f}%）+ Aave supply（{aave_apr:.2f}%）"
                f"= 複合 APR {lido_aave_apy:.2f}%"
            ),
        )

        # 戦略 3: Lido + Pendle PT
        pt_strategy = PendleFixedYieldStrategy()
        pt_eval = await pt_strategy.evaluate(market_info, aave_apr)
        lido_pendle_apy = lido_apr + pt_eval.expected_apy
        lido_pendle = StrategyEvaluation(
            strategy="lido_pendle_pt",
            recommended=pt_eval.recommended,
            expected_apy=lido_pendle_apy,
            risk_level="low",
            details=(
                f"Lido staking（{lido_apr:.2f}%）+ Pendle PT 固定利回り（{pt_eval.expected_apy:.4f}%）"
                f"= 複合 APR {lido_pendle_apy:.4f}%"
            ),
        )

        # 最善戦略を選択（APY が最高のもの）
        all_strategies = [aave_only, lido_aave, lido_pendle]
        best = max(all_strategies, key=lambda s: s.expected_apy)

        logger.info(
            "compare_strategies: aave_only=%.2f%%, lido_aave=%.2f%%, lido_pendle=%.4f%%, best=%s",
            float(aave_only_apy),  # float OK
            float(lido_aave_apy),  # float OK
            float(lido_pendle_apy),  # float OK
            best.strategy,
        )

        return StrategyComparison(
            strategies=all_strategies,
            best_strategy=best.strategy,
            amount=amount,
        )
