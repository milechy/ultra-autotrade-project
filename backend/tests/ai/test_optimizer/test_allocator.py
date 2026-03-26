# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""PortfolioAllocator のテスト。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.optimizer.allocator import PortfolioAllocator
from app.ai.optimizer.net_benefit import ExpectedNetBenefitCalculator
from app.ai.optimizer.schemas import Protocol, Recommendation, StrategyCandidate


@pytest.fixture
def ranked_results(
    sample_candidates: list[StrategyCandidate],
) -> list:
    """ランク付けされた NetBenefitResult のリスト。"""
    calc = ExpectedNetBenefitCalculator()
    return calc.rank_strategies(sample_candidates, Decimal("10000"))


class TestConservativeMode:
    """conservative モードのテスト。"""

    def test_conservative_only_aave_and_idle(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードでは AAVE と IDLE のみ配分されること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        protocols = {e.protocol for e in result.allocations}
        assert protocols <= {Protocol.AAVE, Protocol.IDLE}

    def test_conservative_no_lido_or_pendle(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードでは Lido や Pendle が含まれないこと。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.LIDO not in protocols
        assert Protocol.LIDO_AAVE not in protocols
        assert Protocol.PENDLE_PT not in protocols
        assert Protocol.PENDLE_YT not in protocols

    def test_conservative_aave_gets_95_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで AAVE が 95% 配分されること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        aave_alloc = next(e for e in result.allocations if e.protocol == Protocol.AAVE)
        assert aave_alloc.allocation_pct == Decimal("95")

    def test_conservative_idle_gets_5_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで IDLE が 5% 配分されること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        idle_alloc = next(e for e in result.allocations if e.protocol == Protocol.IDLE)
        assert idle_alloc.allocation_pct == Decimal("5")


class TestBalancedMode:
    """balanced モードのテスト。"""

    def test_balanced_aave_approx_60_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで AAVE が約 60% 配分されること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        aave_alloc = next((e for e in result.allocations if e.protocol == Protocol.AAVE), None)
        assert aave_alloc is not None
        # 正規化により若干ずれる可能性があるため許容範囲を設ける
        assert Decimal("55") <= aave_alloc.allocation_pct <= Decimal("65")

    def test_balanced_no_pendle_yt(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードでは PENDLE_YT が含まれないこと。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.PENDLE_YT not in protocols

    def test_balanced_has_lido_aave(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで LIDO_AAVE が含まれること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.LIDO_AAVE in protocols


class TestAggressiveMode:
    """aggressive モードのテスト。"""

    def test_aggressive_includes_pendle_yt(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで PENDLE_YT が含まれること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.PENDLE_YT in protocols

    def test_aggressive_pendle_yt_max_10_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで PENDLE_YT が 10% 以下であること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        yt_alloc = next((e for e in result.allocations if e.protocol == Protocol.PENDLE_YT), None)
        if yt_alloc is not None:
            assert yt_alloc.allocation_pct <= Decimal("10")


class TestConstraints:
    """配分制約のテスト。"""

    def test_allocations_sum_to_100_conservative(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで配分合計が 100% になること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    def test_allocations_sum_to_100_balanced(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで配分合計が 100% になること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    def test_allocations_sum_to_100_aggressive(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで配分合計が 100% になること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    def test_idle_always_at_least_5_pct_conservative(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで IDLE が常に 5% 以上であること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        idle = next((e for e in result.allocations if e.protocol == Protocol.IDLE), None)
        assert idle is not None
        assert idle.allocation_pct >= Decimal("5")

    def test_avoid_protocols_get_zero_allocation(
        self,
        allocator: PortfolioAllocator,
        sample_candidates: list[StrategyCandidate],
    ) -> None:
        """AVOID 推奨のプロトコルが 0% 配分されること。"""
        from app.ai.optimizer.schemas import NetBenefitResult

        # Pendle YT を AVOID に設定した ranked_results を作成
        ranked = [
            NetBenefitResult(
                protocol=Protocol.AAVE,
                asset="USDC",
                expected_net_benefit=Decimal("10"),
                gross_yield=Decimal("12"),
                total_cost=Decimal("2"),
                risk_adjusted_yield=Decimal("11.4"),
                rank=1,
                recommendation=Recommendation.BUY,
            ),
            NetBenefitResult(
                protocol=Protocol.LIDO_AAVE,
                asset="stETH",
                expected_net_benefit=Decimal("8"),
                gross_yield=Decimal("11"),
                total_cost=Decimal("3"),
                risk_adjusted_yield=Decimal("8.8"),
                rank=2,
                recommendation=Recommendation.BUY,
            ),
            NetBenefitResult(
                protocol=Protocol.PENDLE_PT,
                asset="stETH",
                expected_net_benefit=Decimal("-5"),
                gross_yield=Decimal("5"),
                total_cost=Decimal("10"),
                risk_adjusted_yield=Decimal("4.5"),
                rank=3,
                recommendation=Recommendation.AVOID,  # AVOID!
            ),
            NetBenefitResult(
                protocol=Protocol.LIDO,
                asset="ETH",
                expected_net_benefit=Decimal("3"),
                gross_yield=Decimal("8"),
                total_cost=Decimal("5"),
                risk_adjusted_yield=Decimal("6.8"),
                rank=4,
                recommendation=Recommendation.BUY,
            ),
            NetBenefitResult(
                protocol=Protocol.PENDLE_YT,
                asset="stETH",
                expected_net_benefit=Decimal("-15"),
                gross_yield=Decimal("8"),
                total_cost=Decimal("10"),
                risk_adjusted_yield=Decimal("5.6"),
                rank=5,
                recommendation=Recommendation.AVOID,  # AVOID!
            ),
        ]
        result = allocator.allocate(ranked, Decimal("10000"), "balanced")
        for entry in result.allocations:
            if entry.protocol in (Protocol.PENDLE_PT, Protocol.PENDLE_YT):
                assert entry.allocation_pct == Decimal("0"), (
                    f"{entry.protocol} should be 0% but got {entry.allocation_pct}%"
                )

    def test_explanation_is_non_empty(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """説明文が空でないこと。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        assert result.explanation
        assert len(result.explanation) > 0

    def test_explanation_contains_no_english_jargon(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """説明文に英語の専門用語が含まれないこと。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        jargon = ["APY", "yield", "protocol", "leverage", "staking", "liquidity"]
        for term in jargon:
            assert term not in result.explanation, (
                f"Jargon '{term}' found in explanation: {result.explanation}"
            )

    def test_all_amounts_are_decimal(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """全ての金額が Decimal 型であること。"""
        result = allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        for entry in result.allocations:
            assert isinstance(entry.allocation_pct, Decimal)
            assert isinstance(entry.amount_usd, Decimal)
            assert isinstance(entry.expected_apy, Decimal)
        assert isinstance(result.total_expected_apy, Decimal)
        assert isinstance(result.total_risk_score, Decimal)
