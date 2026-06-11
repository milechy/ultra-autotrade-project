# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""戦略スコアリングモジュール。各プロトコルの StrategyCandidate を生成する。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .schemas import Protocol, StrategyCandidate
from .signal_adapter import LidoSignalAdapter, PendleSignalAdapter

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# risk_mode ごとのリスクペナルティ乗数
# --------------------------------------------------------------------------- #
_RISK_WEIGHT: dict[str, Decimal] = {
    "conservative": Decimal("1.5"),  # ペナルティを強化
    "balanced": Decimal("1.0"),  # デフォルト
    "aggressive": Decimal("0.7"),  # ペナルティを緩和
}
_DEFAULT_RISK_WEIGHT = Decimal("1.0")  # 未知の risk_mode 時のデフォルト


class StrategyScorer:
    """各プロトコルの現在状態から StrategyCandidate を生成するクラス。

    このクラスはダミー/推定値を使用する（実際のプロトコルクライアントには接続しない）。
    本番環境では実際のプロトコルクライアントを使用してデータを取得する。

    adapter を注入した場合は実データ優先、なければダミー定数を使用する。
    adapter なし（デフォルト）で生成した場合、従来と同じ動作（後方互換）。
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

    def __init__(
        self,
        pendle_adapter: Optional[PendleSignalAdapter] = None,
        lido_adapter: Optional[LidoSignalAdapter] = None,
        risk_mode: str = "balanced",
    ) -> None:
        """StrategyScorer を初期化する。

        Args:
            pendle_adapter: Pendle シグナルアダプター。None の場合はダミー定数を使用。
            lido_adapter: Lido シグナルアダプター。None の場合はダミー定数を使用。
            risk_mode: リスクモード（conservative/balanced/aggressive）。
                       ランキングに使用するリスクペナルティ係数を変える。
        """
        self._pendle_adapter = pendle_adapter
        self._lido_adapter = lido_adapter
        self._risk_mode = risk_mode
        self._risk_weight = _RISK_WEIGHT.get(risk_mode, _DEFAULT_RISK_WEIGHT)
        if risk_mode not in _RISK_WEIGHT:
            logger.warning(
                "StrategyScorer: 未知の risk_mode=%s、balanced 相当 (×1.0) を適用", risk_mode
            )

    # ---------------------------------------------------------------------- #
    # 内部ヘルパー
    # ---------------------------------------------------------------------- #

    def _apply_risk_weight(self, base_risk_penalty: Decimal) -> Decimal:
        """risk_mode 重みを適用したリスクペナルティを返す（0-1 にクリップ）。"""
        adjusted = base_risk_penalty * self._risk_weight
        # 0-1 範囲にクリップ
        return min(max(adjusted, Decimal("0")), Decimal("1"))

    # ---------------------------------------------------------------------- #
    # 同期スコアメソッド（adapter なし・後方互換維持）
    # ---------------------------------------------------------------------- #

    def score_aave(self, asset: str = "USDC") -> StrategyCandidate:
        """Aave V3 USDC supply の StrategyCandidate を生成する。"""
        risk_penalty = self._apply_risk_weight(self.RISK_AAVE_USDC)
        logger.debug(
            "score_aave: asset=%s, apy=%s, risk_penalty=%s (mode=%s)",
            asset,
            self.AAVE_USDC_APY,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.AAVE,
            asset=asset,
            expected_apy=self.AAVE_USDC_APY,
            gas_cost_usd=self.GAS_AAVE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_AAVE,
        )

    def score_lido(self) -> StrategyCandidate:
        """Lido stETH ステーキングのみの StrategyCandidate を生成する（同期版）。

        adapter が注入されている場合は score_lido_async() を使うこと。
        """
        risk_penalty = self._apply_risk_weight(self.RISK_LIDO)
        logger.debug(
            "score_lido: apy=%s, risk_penalty=%s (mode=%s)",
            self.LIDO_STAKING_APY,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.LIDO,
            asset="ETH",
            expected_apy=self.LIDO_STAKING_APY,
            gas_cost_usd=self.GAS_LIDO,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_LIDO,
        )

    def score_lido_aave(self) -> StrategyCandidate:
        """Lido + Aave 複合戦略（stETH → Aave supply）の StrategyCandidate を生成する（同期版）。

        APY = Lido staking APY + Aave stETH supply APY
        """
        compound_apy = self.LIDO_STAKING_APY + self.AAVE_STETH_APY
        risk_penalty = self._apply_risk_weight(self.RISK_LIDO_AAVE)
        logger.debug(
            "score_lido_aave: lido=%s + aave_steth=%s = compound=%s, risk_penalty=%s (mode=%s)",
            self.LIDO_STAKING_APY,
            self.AAVE_STETH_APY,
            compound_apy,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.LIDO_AAVE,
            asset="stETH",
            expected_apy=compound_apy,
            gas_cost_usd=self.GAS_LIDO_AAVE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_LIDO,
        )

    def score_pendle_pt(self, market_address: str = "0x_dummy_market") -> StrategyCandidate:
        """Pendle PT 固定利回りの StrategyCandidate を生成する（同期版）。

        APY = PT ディスカウントから implied APY を使用（PoC では PENDLE_IMPLIED_APY を使用）
        固定利回り = (1 - pt_price) / pt_price * (365 / maturity_days) * 100
        """
        risk_penalty = self._apply_risk_weight(self.RISK_PENDLE_PT)
        logger.debug(
            "score_pendle_pt: implied_apy=%s, maturity=%d days, risk_penalty=%s (mode=%s)",
            self.PENDLE_IMPLIED_APY,
            self.PENDLE_MATURITY_DAYS,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_PT,
            asset="stETH",
            expected_apy=self.PENDLE_IMPLIED_APY,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=self.PENDLE_MATURITY_DAYS,
        )

    def score_pendle_yt(self, market_address: str = "0x_dummy_market") -> StrategyCandidate:
        """Pendle YT レバレッジ利回りの StrategyCandidate を生成する（同期版）。

        YT の期待 APY は投機的。高リスクペナルティ（0.30）。
        """
        # YT レバレッジ利回りの推定 APY（投機的）
        yt_expected_apy = Decimal("8.0")
        risk_penalty = self._apply_risk_weight(self.RISK_PENDLE_YT)
        logger.debug(
            "score_pendle_yt: expected_apy=%s, risk_penalty=%s (mode=%s)",
            yt_expected_apy,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=yt_expected_apy,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=self.PENDLE_MATURITY_DAYS,
        )

    def get_all_candidates(self) -> list[StrategyCandidate]:
        """全5プロトコルの候補を取得する: aave, lido, lido_aave, pendle_pt, pendle_yt。

        注: adapter が注入されている場合でも同期メソッドはダミー定数を使用する。
        実データを使う場合は get_all_candidates_async() を使うこと。
        """
        candidates = [
            self.score_aave(),
            self.score_lido(),
            self.score_lido_aave(),
            self.score_pendle_pt(),
            self.score_pendle_yt(),
        ]
        logger.info("get_all_candidates: %d candidates generated", len(candidates))
        return candidates

    # ---------------------------------------------------------------------- #
    # 非同期スコアメソッド（adapter から実データ取得）
    # ---------------------------------------------------------------------- #

    async def score_lido_async(self) -> StrategyCandidate:
        """Lido stETH ステーキングの StrategyCandidate を生成する（adapter 優先）。

        adapter が注入されている場合は実データ（APY）を使用する。
        """
        if self._lido_adapter is not None:
            apy = await self._lido_adapter.get_staking_apy()
            peg_dev = await self._lido_adapter.get_peg_deviation()
        else:
            apy = self.LIDO_STAKING_APY
            peg_dev = Decimal("0")

        risk_penalty = self._apply_risk_weight(self.RISK_LIDO)
        logger.debug(
            "score_lido_async: apy=%s, peg_dev=%s, risk_penalty=%s (mode=%s)",
            apy,
            peg_dev,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.LIDO,
            asset="ETH",
            expected_apy=apy,
            gas_cost_usd=self.GAS_LIDO,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_LIDO,
            peg_deviation=peg_dev,
        )

    async def score_lido_aave_async(self) -> StrategyCandidate:
        """Lido + Aave 複合戦略の StrategyCandidate を生成する（adapter 優先）。"""
        if self._lido_adapter is not None:
            lido_apy = await self._lido_adapter.get_staking_apy()
        else:
            lido_apy = self.LIDO_STAKING_APY

        compound_apy = lido_apy + self.AAVE_STETH_APY
        risk_penalty = self._apply_risk_weight(self.RISK_LIDO_AAVE)
        logger.debug(
            "score_lido_aave_async: lido=%s + aave_steth=%s = compound=%s, risk_penalty=%s (mode=%s)",
            lido_apy,
            self.AAVE_STETH_APY,
            compound_apy,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.LIDO_AAVE,
            asset="stETH",
            expected_apy=compound_apy,
            gas_cost_usd=self.GAS_LIDO_AAVE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_LIDO,
        )

    async def score_pendle_pt_async(
        self, market_address: str = "0x_dummy_market"
    ) -> StrategyCandidate:
        """Pendle PT の StrategyCandidate を生成する（adapter 優先）。"""
        if self._pendle_adapter is not None:
            apy = await self._pendle_adapter.get_pt_apy()
            maturity_days = await self._pendle_adapter.get_maturity_days()
        else:
            apy = self.PENDLE_IMPLIED_APY
            maturity_days = self.PENDLE_MATURITY_DAYS

        risk_penalty = self._apply_risk_weight(self.RISK_PENDLE_PT)
        logger.debug(
            "score_pendle_pt_async: apy=%s, maturity=%d, risk_penalty=%s (mode=%s)",
            apy,
            maturity_days,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_PT,
            asset="stETH",
            expected_apy=apy,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=maturity_days,
        )

    async def score_pendle_yt_async(
        self, market_address: str = "0x_dummy_market"
    ) -> StrategyCandidate:
        """Pendle YT の StrategyCandidate を生成する（adapter 優先）。"""
        if self._pendle_adapter is not None:
            apy = await self._pendle_adapter.get_yt_apy()
            maturity_days = await self._pendle_adapter.get_maturity_days()
        else:
            apy = Decimal("8.0")
            maturity_days = self.PENDLE_MATURITY_DAYS

        risk_penalty = self._apply_risk_weight(self.RISK_PENDLE_YT)
        logger.debug(
            "score_pendle_yt_async: apy=%s, maturity=%d, risk_penalty=%s (mode=%s)",
            apy,
            maturity_days,
            risk_penalty,
            self._risk_mode,
        )
        return StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=apy,
            gas_cost_usd=self.GAS_PENDLE,
            bridge_cost_usd=Decimal("0"),
            risk_penalty=risk_penalty,
            liquidity_available=self.LIQUIDITY_PENDLE,
            maturity_days=maturity_days,
        )

    async def get_all_candidates_async(self) -> list[StrategyCandidate]:
        """全5プロトコルの候補を取得する（adapter から実データ取得・非同期版）。

        adapter が注入されていれば Lido/Pendle は実データ優先。なければダミー定数。

        注意（M3 非対称・暫定）: Aave は本メソッドでも score_aave()（同期・ダミー APY
        AAVE_USDC_APY=4.5）を継続使用する。Aave 実 APY 取得 adapter は未実装のため、
        adapter 注入時は Aave だけダミー / Lido・Pendle だけ実 APY という非対称が生じる。
        Aave 側の実 APY 化は next-PR（router docstring TODO 参照）で対応する。
        本メソッド自体も現状 router の sync compare() からは未配線。
        """
        candidates = [
            self.score_aave(),
            await self.score_lido_async(),
            await self.score_lido_aave_async(),
            await self.score_pendle_pt_async(),
            await self.score_pendle_yt_async(),
        ]
        logger.info("get_all_candidates_async: %d candidates generated", len(candidates))
        return candidates
