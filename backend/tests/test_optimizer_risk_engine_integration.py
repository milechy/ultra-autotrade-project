# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""AI Optimizer + Risk Engine 統合テスト (Lane A-4 staging E2E)。

テスト対象:
  - StrategyScorer → ExpectedNetBenefitCalculator → PortfolioAllocator の完全パイプライン
  - ENB 計算式の精度検証（Formula: gross_yield - risk_penalty_amount - total_cost）
  - リスクシナリオ (LOW/MEDIUM/HIGH) によるプロトコル選好動的変化
  - リスクモード別 (conservative/balanced/aggressive) 配分検証
  - StrategyComparator.compare() + generate_report() フルパイプライン
  - フォールバック → 動的リスクスコア切替の挙動
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.optimizer.allocator import PortfolioAllocator
from app.ai.optimizer.comparator import StrategyComparator
from app.ai.optimizer.net_benefit import ExpectedNetBenefitCalculator
from app.ai.optimizer.schemas import Protocol, Recommendation, StrategyCandidate
from app.ai.optimizer.strategy_scorer import StrategyScorer

# ENB 計算精度の許容誤差
_TOLERANCE = Decimal("0.01")

# 標準テスト投資額・保有日数
_INVESTMENT = Decimal("10000")
_HOLDING_DAYS = 30


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scorer() -> StrategyScorer:
    return StrategyScorer()


@pytest.fixture
def calculator() -> ExpectedNetBenefitCalculator:
    return ExpectedNetBenefitCalculator()


@pytest.fixture
def allocator() -> PortfolioAllocator:
    return PortfolioAllocator()


@pytest.fixture
def comparator() -> StrategyComparator:
    return StrategyComparator()


@pytest.fixture
def all_candidates(scorer: StrategyScorer) -> list[StrategyCandidate]:
    """StrategyScorer から生成した実データ（5プロトコル）。"""
    return scorer.get_all_candidates()


@pytest.fixture
def ranked_results(
    all_candidates: list[StrategyCandidate],
    calculator: ExpectedNetBenefitCalculator,
) -> list:
    """$10,000 / 30日 でランク付けされた NetBenefitResult。"""
    return calculator.rank_strategies(all_candidates, _INVESTMENT, _HOLDING_DAYS)


# ---------------------------------------------------------------------------
# Phase 1: ENB 計算式の精度検証
# ---------------------------------------------------------------------------


class TestENBFormulaAccuracy:
    """期待ネット利益（ENB）の計算式が正しいことを検証する。

    計算式:
        gross_yield = investment * (apy/100) * (holding_days/365)
        risk_penalty_amount = gross_yield * risk_penalty
        risk_adjusted_yield = gross_yield - risk_penalty_amount
        net_benefit = risk_adjusted_yield - (gas_cost + bridge_cost)
    """

    def test_aave_gross_yield(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """Aave USDC のグロス利回りが正確に計算されること。

        10000 * (4.5/100) * (30/365) = 36.986...
        """
        candidate = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("4.5"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.05"),
            liquidity_available=Decimal("1000000000"),
        )
        result = calculator.calculate(candidate, _INVESTMENT, _HOLDING_DAYS)

        expected_gross = (
            Decimal("10000") * Decimal("4.5") / Decimal("100") * Decimal("30") / Decimal("365")
        )
        assert abs(result.gross_yield - expected_gross) < _TOLERANCE

    def test_aave_net_benefit(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """Aave USDC の ENB が正確に計算されること。

        gross=36.986, risk_adj=36.986*0.95=35.137, net=35.137-2.0=33.137
        """
        candidate = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("4.5"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.05"),
            liquidity_available=Decimal("1000000000"),
        )
        result = calculator.calculate(candidate, _INVESTMENT, _HOLDING_DAYS)

        expected_net = Decimal("33.14")
        assert abs(result.expected_net_benefit - expected_net) < Decimal("0.02")
        assert result.recommendation == Recommendation.STRONG_BUY

    def test_pendle_yt_net_benefit_large_investment(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """大額投資 ($10,000) では Pendle YT が STRONG_BUY になること。

        gross=65.753, risk_adj=65.753*0.70=46.027, net=46.027-10.0=36.027
        gross*0.5=32.876 < 36.027 → STRONG_BUY
        """
        candidate = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("8.0"),
            gas_cost_usd=Decimal("10.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),
            liquidity_available=Decimal("100000000"),
            maturity_days=30,
        )
        result = calculator.calculate(candidate, _INVESTMENT, _HOLDING_DAYS)

        expected_net = Decimal("36.03")
        assert abs(result.expected_net_benefit - expected_net) < Decimal("0.05")
        assert result.recommendation == Recommendation.STRONG_BUY

    def test_pendle_yt_hold_small_investment(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """小額投資 ($100) では Pendle YT がガスコスト > 期待利益となり HOLD になること。

        gross=0.657, net=0.460-10.0=-9.54 → -9.54 > -10.0 → HOLD
        """
        candidate = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("8.0"),
            gas_cost_usd=Decimal("10.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),
            liquidity_available=Decimal("100000000"),
            maturity_days=30,
        )
        result = calculator.calculate(candidate, Decimal("100"), _HOLDING_DAYS)

        assert result.expected_net_benefit < Decimal("0")
        assert result.recommendation == Recommendation.HOLD

    def test_risk_penalty_reduces_net_benefit(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """リスクペナルティが高いほど ENB が低くなること（同APY・同ガスの比較）。"""
        base = dict(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("5.0"),
            bridge_cost_usd=Decimal("0"),
            liquidity_available=Decimal("1000000"),
        )
        low_risk = calculator.calculate(
            StrategyCandidate(**base, risk_penalty=Decimal("0.05")),
            _INVESTMENT,
            _HOLDING_DAYS,
        )
        high_risk = calculator.calculate(
            StrategyCandidate(**base, risk_penalty=Decimal("0.40")),
            _INVESTMENT,
            _HOLDING_DAYS,
        )

        assert low_risk.expected_net_benefit > high_risk.expected_net_benefit

    def test_all_decimal_types(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """NetBenefitResult の全フィールドが Decimal 型であること（float 混入なし）。"""
        candidate = StrategyCandidate(
            protocol=Protocol.LIDO_AAVE,
            asset="stETH",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("8.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.20"),
            liquidity_available=Decimal("500000000"),
        )
        result = calculator.calculate(candidate, _INVESTMENT, _HOLDING_DAYS)

        assert isinstance(result.expected_net_benefit, Decimal)
        assert isinstance(result.gross_yield, Decimal)
        assert isinstance(result.total_cost, Decimal)
        assert isinstance(result.risk_adjusted_yield, Decimal)
        assert not isinstance(result.expected_net_benefit, float)


# ---------------------------------------------------------------------------
# Phase 2: 全パイプライン StrategyScorer → Calculator → Allocator
# ---------------------------------------------------------------------------


class TestFullPipelineE2E:
    """StrategyScorer → Calculator → Allocator の完全パイプライン E2E 検証。"""

    def test_scorer_returns_5_protocols(self, all_candidates: list[StrategyCandidate]) -> None:
        """StrategyScorer が 5 つのプロトコル候補を返すこと。"""
        assert len(all_candidates) == 5
        protocols = {c.protocol for c in all_candidates}
        expected = {
            Protocol.AAVE,
            Protocol.LIDO,
            Protocol.LIDO_AAVE,
            Protocol.PENDLE_PT,
            Protocol.PENDLE_YT,
        }
        assert protocols == expected

    def test_ranking_assigns_unique_ranks(self, ranked_results: list) -> None:
        """ランク付けで 1〜5 の連続した一意のランクが割り当てられること。"""
        ranks = [r.rank for r in ranked_results]
        assert sorted(ranks) == [1, 2, 3, 4, 5]

    def test_pendle_yt_is_rank1_large_investment(self, ranked_results: list) -> None:
        """$10,000 / 30日 では Pendle YT が最高 ENB (rank=1) になること。

        Pendle YT: APY=8%, risk_penalty=0.30, gas=$10
        net_benefit ≈ $36.03 が最大。
        """
        rank1 = next(r for r in ranked_results if r.rank == 1)
        assert rank1.protocol == Protocol.PENDLE_YT

    def test_aave_is_rank2_large_investment(self, ranked_results: list) -> None:
        """$10,000 / 30日 では Aave USDC が rank=2 になること。

        Aave: APY=4.5%, risk_penalty=0.05, gas=$2 → net ≈ $33.14
        低ガスコストと低リスクペナルティで PENDLE_YT に次ぐ高効率。
        """
        rank2 = next(r for r in ranked_results if r.rank == 2)
        assert rank2.protocol == Protocol.AAVE

    def test_lido_is_rank5_large_investment(self, ranked_results: list) -> None:
        """$10,000 / 30日 では Lido が最低ランク (rank=5) になること。

        Lido: APY=3.5%, risk_penalty=0.15, gas=$5 → net ≈ $19.45
        """
        rank5 = next(r for r in ranked_results if r.rank == 5)
        assert rank5.protocol == Protocol.LIDO

    def test_net_benefit_decreasing_order(self, ranked_results: list) -> None:
        """rank=1 から rank=5 に向かって ENB が単調減少していること。"""
        sorted_by_rank = sorted(ranked_results, key=lambda r: r.rank)
        for i in range(len(sorted_by_rank) - 1):
            assert (
                sorted_by_rank[i].expected_net_benefit >= sorted_by_rank[i + 1].expected_net_benefit
            )

    def test_all_strong_buy_large_investment(self, ranked_results: list) -> None:
        """$10,000 / 30日 では全プロトコルが STRONG_BUY になること。"""
        for result in ranked_results:
            assert result.recommendation == Recommendation.STRONG_BUY, (
                f"{result.protocol.value}: expected STRONG_BUY, got {result.recommendation.value}"
            )

    def test_all_hold_small_investment(
        self,
        all_candidates: list[StrategyCandidate],
        calculator: ExpectedNetBenefitCalculator,
    ) -> None:
        """$100 / 30日 では全プロトコルが HOLD になること（ガスコストが利益を上回る）。"""
        small_ranked = calculator.rank_strategies(all_candidates, Decimal("100"), _HOLDING_DAYS)
        for result in small_ranked:
            assert result.recommendation == Recommendation.HOLD, (
                f"{result.protocol.value}: expected HOLD, got {result.recommendation.value}"
            )

    def test_aave_rank1_small_investment(
        self,
        all_candidates: list[StrategyCandidate],
        calculator: ExpectedNetBenefitCalculator,
    ) -> None:
        """$100 の小額投資では Aave が rank=1 になること（低ガスコスト優位）。"""
        small_ranked = calculator.rank_strategies(all_candidates, Decimal("100"), _HOLDING_DAYS)
        rank1 = next(r for r in small_ranked if r.rank == 1)
        assert rank1.protocol == Protocol.AAVE

    @pytest.mark.asyncio
    async def test_full_pipeline_conservative(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """conservative モードでフルパイプラインが正常に完了すること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            allocation = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        assert allocation is not None
        assert len(allocation.allocations) > 0
        # 配分合計が 100% になること
        total_pct = sum(e.allocation_pct for e in allocation.allocations)
        assert abs(total_pct - Decimal("100")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_full_pipeline_aggressive(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """aggressive モードでフルパイプラインが正常に完了すること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            allocation = await allocator.allocate(ranked_results, _INVESTMENT, "aggressive")

        assert allocation is not None
        total_pct = sum(e.allocation_pct for e in allocation.allocations)
        assert abs(total_pct - Decimal("100")) < Decimal("0.01")


# ---------------------------------------------------------------------------
# Phase 3: リスクシナリオ (HIGH/MEDIUM/LOW) によるプロトコル選好変化
# ---------------------------------------------------------------------------


class TestRiskScenarios:
    """リスクエンジンの HIGH/MEDIUM/LOW 切替によるリスクスコア動的変化を検証する。"""

    def _make_risk_map(self, level: str) -> dict[Protocol, Decimal]:
        """指定レベルの均一リスクマップを生成する。"""
        score_map = {"low": Decimal("0.05"), "medium": Decimal("0.25"), "high": Decimal("0.60")}
        score = score_map[level]
        return {
            Protocol.AAVE: score,
            Protocol.LIDO: score,
            Protocol.LIDO_AAVE: score,
            Protocol.PENDLE_PT: score,
            Protocol.PENDLE_YT: score,
            Protocol.IDLE: Decimal("0.00"),
        }

    @pytest.mark.asyncio
    async def test_low_risk_scenario_conservative(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """LOW リスク + conservative → 総合リスクスコアが低い (< 0.10)。

        conservative: AAVE=95%, IDLE=5%
        risk_score = 0.05 * 0.95 + 0.00 * 0.05 = 0.0475
        """
        low_map = self._make_risk_map("low")
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=low_map),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        assert result.total_risk_score < Decimal("0.10")
        expected = Decimal("0.0475")
        assert abs(result.total_risk_score - expected) < Decimal("0.005")

    @pytest.mark.asyncio
    async def test_high_risk_scenario_conservative(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """HIGH リスク + conservative → 総合リスクスコアが高い (> 0.50)。

        conservative: AAVE=95%, IDLE=5%
        risk_score = 0.60 * 0.95 + 0.00 * 0.05 = 0.57
        """
        high_map = self._make_risk_map("high")
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=high_map),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        assert result.total_risk_score > Decimal("0.50")
        expected = Decimal("0.57")
        assert abs(result.total_risk_score - expected) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_medium_risk_scenario_conservative(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """MEDIUM リスク + conservative → リスクスコアが LOW < MEDIUM < HIGH の順序。

        conservative: AAVE=95%, IDLE=5%
        risk_score = 0.25 * 0.95 + 0.00 * 0.05 = 0.2375
        """
        medium_map = self._make_risk_map("medium")
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=medium_map),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        expected = Decimal("0.2375")
        assert abs(result.total_risk_score - expected) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_risk_score_ordering_low_medium_high(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """LOW < MEDIUM < HIGH の順でリスクスコアが増加すること。"""
        scores = {}
        for level in ("low", "medium", "high"):
            risk_map = self._make_risk_map(level)
            with patch(
                "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
                new=AsyncMock(return_value=risk_map),
            ):
                result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")
            scores[level] = result.total_risk_score

        assert scores["low"] < scores["medium"] < scores["high"], (
            f"Expected LOW<MEDIUM<HIGH: {scores}"
        )

    @pytest.mark.asyncio
    async def test_risk_score_all_decimal_in_scenarios(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """全シナリオで total_risk_score が Decimal 型であること。"""
        for level in ("low", "medium", "high"):
            risk_map = self._make_risk_map(level)
            with patch(
                "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
                new=AsyncMock(return_value=risk_map),
            ):
                result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

            assert isinstance(result.total_risk_score, Decimal), (
                f"level={level}: total_risk_score is {type(result.total_risk_score)}"
            )
            assert not isinstance(result.total_risk_score, float)


# ---------------------------------------------------------------------------
# Phase 4: リスクモード別プロトコル配分検証
# ---------------------------------------------------------------------------


class TestProtocolAllocationByRiskMode:
    """conservative/balanced/aggressive 各モードのプロトコル配分を検証する。"""

    @pytest.mark.asyncio
    async def test_conservative_aave_95pct(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """conservative モード: AAVE が 95% 配分されること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        aave_entry = next((e for e in result.allocations if e.protocol == Protocol.AAVE), None)
        assert aave_entry is not None
        assert abs(aave_entry.allocation_pct - Decimal("95")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_conservative_idle_5pct(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """conservative モード: IDLE が 5% 配分されること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        idle_entry = next((e for e in result.allocations if e.protocol == Protocol.IDLE), None)
        assert idle_entry is not None
        assert abs(idle_entry.allocation_pct - Decimal("5")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_conservative_no_pendle(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """conservative モード: Pendle (PT/YT) が配分されないこと。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        pendle_entries = [
            e for e in result.allocations if e.protocol in (Protocol.PENDLE_PT, Protocol.PENDLE_YT)
        ]
        assert len(pendle_entries) == 0

    @pytest.mark.asyncio
    async def test_balanced_includes_lido_aave(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """balanced モード: LIDO_AAVE が配分に含まれること（25%）。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        lido_aave_entry = next(
            (e for e in result.allocations if e.protocol == Protocol.LIDO_AAVE), None
        )
        assert lido_aave_entry is not None
        assert abs(lido_aave_entry.allocation_pct - Decimal("25")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_balanced_no_pendle_yt(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """balanced モード: PENDLE_YT が配分されないこと。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        yt_entry = next((e for e in result.allocations if e.protocol == Protocol.PENDLE_YT), None)
        assert yt_entry is None

    @pytest.mark.asyncio
    async def test_aggressive_includes_pendle_yt(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """aggressive モード: PENDLE_YT が最大 10% 配分されること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "aggressive")

        yt_entry = next((e for e in result.allocations if e.protocol == Protocol.PENDLE_YT), None)
        assert yt_entry is not None
        # YT キャップ: <= 10%
        assert yt_entry.allocation_pct <= Decimal("10")

    @pytest.mark.asyncio
    async def test_all_modes_total_100pct(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """全リスクモードで配分合計が 100% になること。"""
        for mode in ("conservative", "balanced", "aggressive"):
            with patch(
                "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
                new=AsyncMock(return_value=None),
            ):
                result = await allocator.allocate(ranked_results, _INVESTMENT, mode)

            total_pct = sum(e.allocation_pct for e in result.allocations)
            assert abs(total_pct - Decimal("100")) < Decimal("0.01"), (
                f"mode={mode}: total_pct={total_pct}"
            )

    @pytest.mark.asyncio
    async def test_all_modes_min_idle_5pct(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """全リスクモードで IDLE が >= 5% 維持されること。"""
        for mode in ("conservative", "balanced", "aggressive"):
            with patch(
                "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
                new=AsyncMock(return_value=None),
            ):
                result = await allocator.allocate(ranked_results, _INVESTMENT, mode)

            idle_entry = next((e for e in result.allocations if e.protocol == Protocol.IDLE), None)
            assert idle_entry is not None, f"mode={mode}: IDLE entry missing"
            assert idle_entry.allocation_pct >= Decimal("5"), (
                f"mode={mode}: IDLE={idle_entry.allocation_pct}% < 5%"
            )

    @pytest.mark.asyncio
    async def test_amount_usd_matches_pct(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """amount_usd が allocation_pct * investment / 100 と一致すること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        for entry in result.allocations:
            expected_amount = _INVESTMENT * entry.allocation_pct / Decimal("100")
            assert abs(entry.amount_usd - expected_amount) < Decimal("0.01"), (
                f"{entry.protocol.value}: amount_usd={entry.amount_usd}, expected={expected_amount}"
            )


# ---------------------------------------------------------------------------
# Phase 5: StrategyComparator フルパイプライン
# ---------------------------------------------------------------------------


class TestStrategyComparatorPipeline:
    """StrategyComparator.compare() + generate_report() の完全パイプライン検証。"""

    def test_compare_returns_strategy_comparison(self, comparator: StrategyComparator) -> None:
        """compare() が StrategyComparison を返すこと。"""
        from app.ai.optimizer.schemas import StrategyComparison

        result = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)

        assert isinstance(result, StrategyComparison)
        assert len(result.candidates) == 5

    def test_recommended_is_rank1(self, comparator: StrategyComparator) -> None:
        """recommended が candidates 中の rank=1 の結果であること。"""
        result = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)

        assert result.recommended.rank == 1
        # candidates の中で最大 ENB を持つプロトコルが推奨されること
        max_benefit = max(c.expected_net_benefit for c in result.candidates)
        assert result.recommended.expected_net_benefit == max_benefit

    def test_idle_benefit_is_zero(self, comparator: StrategyComparator) -> None:
        """idle_benefit（何もしない場合の利益）は 0 であること。"""
        result = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)

        assert result.idle_benefit == Decimal("0")

    def test_comparison_timestamp_is_utc_iso(self, comparator: StrategyComparator) -> None:
        """comparison_timestamp が ISO 形式の UTC 文字列であること。"""
        from datetime import datetime

        result = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)

        # ISO 形式でパース可能であること
        parsed = datetime.fromisoformat(result.comparison_timestamp)
        assert parsed is not None

    def test_generate_report_contains_japanese(self, comparator: StrategyComparator) -> None:
        """generate_report() が日本語のレポートを返すこと。"""
        comparison = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)
        report = comparator.generate_report(comparison, "conservative")

        assert "推奨" in report
        assert "戦略比較レポート" in report
        assert "期待利益" in report

    def test_generate_report_conservative_mode(self, comparator: StrategyComparator) -> None:
        """conservative モードのレポートに 'conservative' が含まれること。"""
        comparison = comparator.compare(_INVESTMENT, "conservative", _HOLDING_DAYS)
        report = comparator.generate_report(comparison, "conservative")

        assert "conservative" in report

    def test_generate_report_includes_ranking(self, comparator: StrategyComparator) -> None:
        """レポートに全プロトコルのランキングが含まれること（5件）。"""
        comparison = comparator.compare(_INVESTMENT, "balanced", _HOLDING_DAYS)
        report = comparator.generate_report(comparison, "balanced")

        # 5プロトコルが「1.」〜「5.」形式でランキング表示されること
        for i in range(1, 6):
            assert f"{i}." in report, f"Ranking entry {i} not found in report"

    def test_compare_balanced_returns_all_candidates(self, comparator: StrategyComparator) -> None:
        """balanced モードでも全 5 プロトコルが比較対象に含まれること。"""
        result = comparator.compare(_INVESTMENT, "balanced", _HOLDING_DAYS)

        protocols = {c.protocol for c in result.candidates}
        expected = {
            Protocol.AAVE,
            Protocol.LIDO,
            Protocol.LIDO_AAVE,
            Protocol.PENDLE_PT,
            Protocol.PENDLE_YT,
        }
        assert protocols == expected

    def test_compare_disclaimer_in_report(self, comparator: StrategyComparator) -> None:
        """レポートに免責事項（※）が含まれること。"""
        comparison = comparator.compare(_INVESTMENT, "aggressive", _HOLDING_DAYS)
        report = comparator.generate_report(comparison, "aggressive")

        assert "※" in report


# ---------------------------------------------------------------------------
# Phase 6: フォールバック → 動的リスクスコア切替
# ---------------------------------------------------------------------------


class TestFallbackToDynamicSwitch:
    """フォールバック固定値から動的リスクスコアへの切替挙動を検証する。"""

    @pytest.mark.asyncio
    async def test_fallback_risk_score_conservative(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """フォールバック時、conservative では AAVE(0.05)*0.95 + IDLE(0.00)*0.05 = 0.0475。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "conservative")

        expected = Decimal("0.05") * Decimal("95") / Decimal("100")
        assert abs(result.total_risk_score - expected) < Decimal("0.001")

    @pytest.mark.asyncio
    async def test_dynamic_low_better_than_fallback_for_high_risk_protocols(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """dynamic LOW マップ使用時、balanced のリスクスコアがフォールバックより低くなること。

        balanced テンプレート: AAVE=60%, LIDO_AAVE=25%, PENDLE_PT=10%, IDLE=5%
        fallback: AAVE=0.05, LIDO_AAVE=0.20, PENDLE_PT=0.10, IDLE=0.00
        fallback risk = 0.05*0.60 + 0.20*0.25 + 0.10*0.10 + 0.00*0.05
                      = 0.030 + 0.050 + 0.010 + 0.000 = 0.090

        dynamic LOW: all=0.05 (IDLE=0.00)
        dynamic risk = 0.05*0.60 + 0.05*0.25 + 0.05*0.10 + 0.00*0.05
                     = 0.030 + 0.0125 + 0.005 + 0.000 = 0.0475 < 0.090
        """
        low_map = {
            Protocol.AAVE: Decimal("0.05"),
            Protocol.LIDO: Decimal("0.05"),
            Protocol.LIDO_AAVE: Decimal("0.05"),
            Protocol.PENDLE_PT: Decimal("0.05"),
            Protocol.PENDLE_YT: Decimal("0.05"),
            Protocol.IDLE: Decimal("0.00"),
        }

        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            fallback_result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=low_map),
        ):
            dynamic_result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        assert dynamic_result.total_risk_score < fallback_result.total_risk_score

    @pytest.mark.asyncio
    async def test_explanation_is_japanese(
        self,
        ranked_results: list,
        allocator: PortfolioAllocator,
    ) -> None:
        """explanation フィールドが日本語であること。"""
        with patch(
            "app.ai.optimizer.allocator.PortfolioAllocator._build_dynamic_risk_map",
            new=AsyncMock(return_value=None),
        ):
            result = await allocator.allocate(ranked_results, _INVESTMENT, "balanced")

        assert "バランス" in result.explanation or "配分" in result.explanation
        assert "%" in result.explanation
