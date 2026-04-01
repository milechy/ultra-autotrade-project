# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""戦略スコアリングモジュール。各プロトコルの StrategyCandidate を生成する。"""

from __future__ import annotations

import logging
from decimal import Decimal

from .schemas import Protocol, StrategyCandidate

logger = logging.getLogger(__name__)


class StrategyScorer:
    """各プロトコルの現在状態から StrategyCandidate を生成するクラス。

    このクラスはダミー/推定値を使用する（実際のプロトコルクライアントには接続しない）。
    本番環境では実際のプロトコルクライアントを使用してデータを取得する。
    """

    # デフォルト推定値（Lido/Pendle PoC モジュールと同じ値を使用）
    AAVE_USDC_APY: Decimal = Decimal("4.5")  # Aave V3 USDC supply APR
    AAVE_STETH_APY: Decimal = Decimal(
        "1.5"
    )  # Aave stETH supply APR (lido/aave_integration.py より)
    LIDO_STAKING_APY: Decimal = Decimal("3.5")  # Lido staking APR (DummyLidoClient より)
    PENDLE_PT_PRICE: Decimal = Decimal("0.95")  # DummyPendleClient より
    PENDLE_YT_PRICE: Decimal = Decimal("0.05")  # DummyPendleClient より
    PENDLE_MATURITY_DAYS: int = 30  # DummyPendleClient より
    PENDLE_IMPLIED_APY: Decimal = Decimal("5.2")  # DummyPendleClient より

    # ガスコスト見積もり（USD）
    GAS_AAVE: Decimal = Decimal("2.0")
    GAS_LIDO: Decimal = Decimal("5.0")
    GAS_LIDO_AAVE: Decimal = Decimal("8.0")  # Lido stake + Aave supply
    GAS_PENDLE: Decimal = Decimal("10.0")  # Pendle 操作はガスコストが高め

    # リスクペナルティ（0-1 スケール）
    RISK_AAVE_USDC: Decimal = Decimal("0.05")  # 非常に低リスク
    RISK_LIDO: Decimal = Decimal("0.15")  # 中程度: スマートコントラクト + スラッシングリスク
    RISK_LIDO_AAVE: Decimal = Decimal("0.20")  # 中程度: 複合プロトコルリスク
    RISK_PENDLE_PT: Decimal = Decimal("0.10")  # 低〜中程度: 固定利回り、結果が確定
    RISK_PENDLE_YT: Decimal = Decimal("0.30")  # 高: レバレッジ利回りエクスポージャー

    # 流動性見積もり（USD）
    LIQUIDITY_AAVE: Decimal = Decimal("1000000000")  # 10億ドル
    LIQUIDITY_LIDO: Decimal = Decimal("500000000")  # 5億ドル
    LIQUIDITY_PENDLE: Decimal = Decimal("100000000")  # 1億ドル

    def score_aave(self, asset: str = "USDC") -> StrategyCandidate:
        """Aave V3 USDC supply の StrategyCandidate を生成する。"""
        logger.debug("score_aave: asset=%s, apy=%s", asset, self.AAVE_USDC_APY)
        return StrategyCandidate(
            protocol=Protocol.AAVE,
            asset=asset,
            expected_apy=self.AAVE_USDC_APY,
            gas_cost_usd=self.GAS_AAVE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=self.RISK_AAVE_USDC,
            liquidity_available=self.LIQUIDITY_AAVE,
        )

    def score_lido(self) -> StrategyCandidate:
        """Lido stETH ステーキングのみの StrategyCandidate を生成する。"""
        logger.debug("score_lido: apy=%s", self.LIDO_STAKING_APY)
        return StrategyCandidate(
            protocol=Protocol.LIDO,
            asset="ETH",
            expected_apy=self.LIDO_STAKING_APY,
            gas_cost_usd=self.GAS_LIDO,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=self.RISK_LIDO,
            liquidity_available=self.LIQUIDITY_LIDO,
        )

    def score_lido_aave(self) -> StrategyCandidate:
        """Lido + Aave 複合戦略（stETH → Aave supply）の StrategyCandidate を生成する。

        APY = Lido staking APY + Aave stETH supply APY
        """
        compound_apy = self.LIDO_STAKING_APY + self.AAVE_STETH_APY
        logger.debug(
            "score_lido_aave: lido=%s + aave_steth=%s = compound=%s",
            self.LIDO_STAKING_APY,
            self.AAVE_STETH_APY,
            compound_apy,
        )
        return StrategyCandidate(
            protocol=Protocol.LIDO_AAVE,
            asset="stETH",
            expected_apy=compound_apy,
            gas_cost_usd=self.GAS_LIDO_AAVE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=self.RISK_LIDO_AAVE,
            liquidity_available=self.LIQUIDITY_LIDO,
        )

    def score_pendle_pt(self, market_address: str = "0x_dummy_market") -> StrategyCandidate:
        """Pendle PT 固定利回りの StrategyCandidate を生成する。

        APY = PT ディスカウントから implied APY を使用（PoC では PENDLE_IMPLIED_APY を使用）
        固定利回り = (1 - pt_price) / pt_price * (365 / maturity_days) * 100
        """
        logger.debug(
            "score_pendle_pt: implied_apy=%s, maturity=%d days",
            self.PENDLE_IMPLIED_APY,
            self.PENDLE_MATURITY_DAYS,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_PT,
            asset="stETH",
            expected_apy=self.PENDLE_IMPLIED_APY,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=self.RISK_PENDLE_PT,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=self.PENDLE_MATURITY_DAYS,
        )

    def score_pendle_yt(self, market_address: str = "0x_dummy_market") -> StrategyCandidate:
        """Pendle YT レバレッジ利回りの StrategyCandidate を生成する。

        YT の期待 APY は投機的。高リスクペナルティ（0.30）。
        """
        # YT レバレッジ利回りの推定 APY（投機的）
        yt_expected_apy = Decimal("8.0")
        logger.debug(
            "score_pendle_yt: expected_apy=%s, risk_penalty=%s",
            yt_expected_apy,
            self.RISK_PENDLE_YT,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=yt_expected_apy,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=self.RISK_PENDLE_YT,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=self.PENDLE_MATURITY_DAYS,
        )

    def get_all_candidates(self) -> list[StrategyCandidate]:
        """全5プロトコルの候補を取得する: aave, lido, lido_aave, pendle_pt, pendle_yt。"""
        candidates = [
            self.score_aave(),
            self.score_lido(),
            self.score_lido_aave(),
            self.score_pendle_pt(),
            self.score_pendle_yt(),
        ]
        logger.info("get_all_candidates: %d candidates generated", len(candidates))
        return candidates
