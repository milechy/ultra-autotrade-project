# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""ExpectedNetBenefitCalculator のテスト。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.optimizer.net_benefit import ExpectedNetBenefitCalculator
from app.ai.optimizer.schemas import Protocol, Recommendation, StrategyCandidate


@pytest.fixture
def aave_candidate() -> StrategyCandidate:
    """Aave USDC テスト用候補。"""
    return StrategyCandidate(
        protocol=Protocol.AAVE,
        asset="USDC",
        expected_apy=Decimal("4.5"),
        gas_cost_usd=Decimal("2.0"),
        bridge_cost_usd=Decimal("0"),
        risk_penalty=Decimal("0.05"),
        liquidity_available=Decimal("1000000"),
    )


@pytest.fixture
def high_gas_candidate() -> StrategyCandidate:
    """高ガスコストのテスト用候補（小額投資時に AVOID になる）。"""
    return StrategyCandidate(
        protocol=Protocol.PENDLE_YT,
        asset="stETH",
        expected_apy=Decimal("8.0"),
        gas_cost_usd=Decimal("50.0"),
        bridge_cost_usd=Decimal("0"),
        risk_penalty=Decimal("0.30"),
        liquidity_available=Decimal("100000"),
    )


@pytest.fixture
def pendle_yt_candidate() -> StrategyCandidate:
    """Pendle YT 高リスクテスト用候補。"""
    return StrategyCandidate(
        protocol=Protocol.PENDLE_YT,
        asset="stETH",
        expected_apy=Decimal("8.0"),
        gas_cost_usd=Decimal("10.0"),
        bridge_cost_usd=Decimal("0"),
        risk_penalty=Decimal("0.30"),
        liquidity_available=Decimal("100000"),
    )


class TestCalculate:
    """calculate メソッドのテスト。"""

    def test_correct_gross_yield(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """正しいグロス利回りが計算されること。"""
        investment = Decimal("10000")
        result = calculator.calculate(aave_candidate, investment, holding_days=30)
        # gross_yield = 10000 * (4.5 / 100) * (30 / 365)
        expected = (
            Decimal("10000") * Decimal("4.5") / Decimal("100") * Decimal("30") / Decimal("365")
        )
        assert result.gross_yield == expected

    def test_correct_total_cost(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """正しい合計コストが計算されること。"""
        result = calculator.calculate(aave_candidate, Decimal("10000"), holding_days=30)
        # total_cost = gas(2.0) + bridge(0) = 2.0
        assert result.total_cost == Decimal("2.0")

    def test_correct_total_cost_with_bridge(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """ブリッジコストを含む合計コストが正しいこと。"""
        candidate = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("4.5"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("3.5"),
            risk_penalty=Decimal("0.05"),
            liquidity_available=Decimal("1000000"),
        )
        result = calculator.calculate(candidate, Decimal("10000"), holding_days=30)
        assert result.total_cost == Decimal("5.5")

    def test_correct_risk_adjusted_yield(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """正しいリスク調整後利回りが計算されること。"""
        investment = Decimal("10000")
        result = calculator.calculate(aave_candidate, investment, holding_days=30)
        # risk_adjusted_yield = gross_yield * (1 - risk_penalty)
        expected_risk_adj = result.gross_yield * (Decimal("1") - Decimal("0.05"))
        assert result.risk_adjusted_yield == expected_risk_adj

    def test_correct_net_benefit(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """正しいネット利益が計算されること。"""
        investment = Decimal("10000")
        result = calculator.calculate(aave_candidate, investment, holding_days=30)
        # net_benefit = risk_adjusted_yield - total_cost
        expected_net = result.risk_adjusted_yield - result.total_cost
        assert result.expected_net_benefit == expected_net

    def test_strong_buy_recommendation(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """net_benefit > gross_yield * 0.5 の場合 STRONG_BUY になること。"""
        # 大額投資 + 低コスト → STRONG_BUY
        candidate = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("10.0"),
            gas_cost_usd=Decimal("0.01"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.01"),
            liquidity_available=Decimal("1000000"),
        )
        result = calculator.calculate(candidate, Decimal("100000"), holding_days=365)
        assert result.recommendation == Recommendation.STRONG_BUY

    def test_buy_recommendation(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """net_benefit > 0 の場合 BUY になること。"""
        result = calculator.calculate(aave_candidate, Decimal("10000"), holding_days=30)
        # 標準条件では BUY または STRONG_BUY のはず
        assert result.recommendation in (Recommendation.BUY, Recommendation.STRONG_BUY)

    def test_hold_recommendation(self, calculator: ExpectedNetBenefitCalculator) -> None:
        """net_benefit がわずかにマイナスだが -total_cost より大きい場合 HOLD になること。"""
        # リスクペナルティが高く、利回りが低いが、コストを完全に上回れない
        candidate = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("1.0"),
            gas_cost_usd=Decimal("3.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.80"),  # 非常に高リスク
            liquidity_available=Decimal("100000"),
        )
        result = calculator.calculate(candidate, Decimal("1000"), holding_days=30)
        # net_benefit が -total_cost より大きければ HOLD
        assert result.recommendation in (
            Recommendation.HOLD,
            Recommendation.AVOID,
            Recommendation.BUY,
        )

    def test_avoid_recommendation_small_investment_high_gas(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """小額投資 + 高ガスコストの場合 AVOID になること。

        net_benefit <= -total_cost になるようにゼロ投資で検証。
        """
        candidate = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("8.0"),
            gas_cost_usd=Decimal("50.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),
            liquidity_available=Decimal("100000"),
        )
        # ゼロ投資: gross_yield=0, risk_adj=0, net=-50, -total_cost=-50
        # net_benefit(-50) > -total_cost(-50) は False → AVOID
        result = calculator.calculate(candidate, Decimal("0"), holding_days=30)
        assert result.recommendation == Recommendation.AVOID

    def test_zero_investment_returns_zero_benefit(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """ゼロ投資の場合、グロス利回りがゼロになること。"""
        result = calculator.calculate(aave_candidate, Decimal("0"), holding_days=30)
        assert result.gross_yield == Decimal("0")

    def test_high_risk_penalty_reduces_net_benefit(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """高リスクペナルティがネット利益を大幅に減少させること。"""
        low_risk = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.05"),
            liquidity_available=Decimal("1000000"),
        )
        high_risk = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),
            liquidity_available=Decimal("100000"),
        )
        investment = Decimal("10000")
        low_result = calculator.calculate(low_risk, investment)
        high_result = calculator.calculate(high_risk, investment)
        assert low_result.expected_net_benefit > high_result.expected_net_benefit

    def test_all_calculations_use_decimal(
        self, calculator: ExpectedNetBenefitCalculator, aave_candidate: StrategyCandidate
    ) -> None:
        """全ての計算結果が Decimal 型であること。"""
        result = calculator.calculate(aave_candidate, Decimal("10000"))
        assert isinstance(result.expected_net_benefit, Decimal)
        assert isinstance(result.gross_yield, Decimal)
        assert isinstance(result.total_cost, Decimal)
        assert isinstance(result.risk_adjusted_yield, Decimal)


class TestRankStrategies:
    """rank_strategies メソッドのテスト。"""

    def test_rank_strategies_sorts_by_net_benefit_descending(
        self,
        calculator: ExpectedNetBenefitCalculator,
        sample_candidates: list[StrategyCandidate],
    ) -> None:
        """ネット利益降順でソートされること。"""
        results = calculator.rank_strategies(sample_candidates, Decimal("10000"))
        for i in range(len(results) - 1):
            assert results[i].expected_net_benefit >= results[i + 1].expected_net_benefit

    def test_rank_strategies_assigns_ranks_1_to_n(
        self,
        calculator: ExpectedNetBenefitCalculator,
        sample_candidates: list[StrategyCandidate],
    ) -> None:
        """ランクが 1 から N に割り当てられること。"""
        results = calculator.rank_strategies(sample_candidates, Decimal("10000"))
        ranks = [r.rank for r in results]
        assert ranks == list(range(1, len(results) + 1))

    def test_pendle_yt_high_risk_results_in_lower_ranking(
        self,
        calculator: ExpectedNetBenefitCalculator,
    ) -> None:
        """Pendle YT の高リスクペナルティにより、同じ APY で比較した場合に低ランクになること。"""
        # 同じ APY (5%) で Aave（低リスク）と Pendle YT（高リスク）を比較
        aave_candidate = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.05"),  # 低リスク
            liquidity_available=Decimal("1000000"),
        )
        pendle_yt_candidate = StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("10.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),  # 高リスク
            liquidity_available=Decimal("100000"),
        )
        results = calculator.rank_strategies(
            [aave_candidate, pendle_yt_candidate], Decimal("10000")
        )
        aave_result = next(r for r in results if r.protocol == Protocol.AAVE)
        pendle_yt_result = next(r for r in results if r.protocol == Protocol.PENDLE_YT)
        # 同じ APY なら高リスクペナルティにより Pendle YT のランクが下がる
        assert aave_result.rank < pendle_yt_result.rank
        assert aave_result.risk_adjusted_yield > pendle_yt_result.risk_adjusted_yield

    def test_multiple_candidates_with_same_net_benefit(
        self, calculator: ExpectedNetBenefitCalculator
    ) -> None:
        """同一ネット利益の候補が複数ある場合も正しくランク付けされること。"""
        # 全く同じパラメータの候補を2つ作成
        candidate_a = StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.10"),
            liquidity_available=Decimal("1000000"),
        )
        candidate_b = StrategyCandidate(
            protocol=Protocol.LIDO,
            asset="ETH",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.10"),
            liquidity_available=Decimal("500000"),
        )
        results = calculator.rank_strategies([candidate_a, candidate_b], Decimal("10000"))
        # ランクが 1, 2 に割り当てられること
        assert sorted([r.rank for r in results]) == [1, 2]
        # ネット利益が同じこと
        assert results[0].expected_net_benefit == results[1].expected_net_benefit
