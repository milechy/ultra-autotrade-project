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

    @pytest.mark.asyncio
    async def test_conservative_only_aave_and_idle(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードでは AAVE と IDLE のみ配分されること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        protocols = {e.protocol for e in result.allocations}
        assert protocols <= {Protocol.AAVE, Protocol.IDLE}

    @pytest.mark.asyncio
    async def test_conservative_no_lido_or_pendle(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードでは Lido や Pendle が含まれないこと。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.LIDO not in protocols
        assert Protocol.LIDO_AAVE not in protocols
        assert Protocol.PENDLE_PT not in protocols
        assert Protocol.PENDLE_YT not in protocols

    @pytest.mark.asyncio
    async def test_conservative_aave_gets_95_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで AAVE が 95% 配分されること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        aave_alloc = next(e for e in result.allocations if e.protocol == Protocol.AAVE)
        assert aave_alloc.allocation_pct == Decimal("95")

    @pytest.mark.asyncio
    async def test_conservative_idle_gets_5_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで IDLE が 5% 配分されること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        idle_alloc = next(e for e in result.allocations if e.protocol == Protocol.IDLE)
        assert idle_alloc.allocation_pct == Decimal("5")


class TestBalancedMode:
    """balanced モードのテスト。"""

    @pytest.mark.asyncio
    async def test_balanced_aave_approx_60_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで AAVE が約 60% 配分されること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        aave_alloc = next((e for e in result.allocations if e.protocol == Protocol.AAVE), None)
        assert aave_alloc is not None
        # 正規化により若干ずれる可能性があるため許容範囲を設ける
        assert Decimal("55") <= aave_alloc.allocation_pct <= Decimal("65")

    @pytest.mark.asyncio
    async def test_balanced_no_pendle_yt(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードでは PENDLE_YT が含まれないこと。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.PENDLE_YT not in protocols

    @pytest.mark.asyncio
    async def test_balanced_has_lido_aave(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで LIDO_AAVE が含まれること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.LIDO_AAVE in protocols


class TestAggressiveMode:
    """aggressive モードのテスト。"""

    @pytest.mark.asyncio
    async def test_aggressive_includes_pendle_yt(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで PENDLE_YT が含まれること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        protocols = {e.protocol for e in result.allocations}
        assert Protocol.PENDLE_YT in protocols

    @pytest.mark.asyncio
    async def test_aggressive_pendle_yt_max_10_pct(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで PENDLE_YT が 10% 以下であること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        yt_alloc = next((e for e in result.allocations if e.protocol == Protocol.PENDLE_YT), None)
        if yt_alloc is not None:
            assert yt_alloc.allocation_pct <= Decimal("10")


class TestConstraints:
    """配分制約のテスト。"""

    @pytest.mark.asyncio
    async def test_allocations_sum_to_100_conservative(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで配分合計が 100% になること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_allocations_sum_to_100_balanced(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """balanced モードで配分合計が 100% になること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_allocations_sum_to_100_aggressive(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """aggressive モードで配分合計が 100% になること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "aggressive")
        total = sum(e.allocation_pct for e in result.allocations)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_idle_always_at_least_5_pct_conservative(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """conservative モードで IDLE が常に 5% 以上であること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        idle = next((e for e in result.allocations if e.protocol == Protocol.IDLE), None)
        assert idle is not None
        assert idle.allocation_pct >= Decimal("5")

    @pytest.mark.asyncio
    async def test_avoid_protocols_get_zero_allocation(
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
        result = await allocator.allocate(ranked, Decimal("10000"), "balanced")
        for entry in result.allocations:
            if entry.protocol in (Protocol.PENDLE_PT, Protocol.PENDLE_YT):
                assert entry.allocation_pct == Decimal("0"), (
                    f"{entry.protocol} should be 0% but got {entry.allocation_pct}%"
                )

    @pytest.mark.asyncio
    async def test_explanation_is_non_empty(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """説明文が空でないこと。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        assert result.explanation
        assert len(result.explanation) > 0

    @pytest.mark.asyncio
    async def test_explanation_contains_no_english_jargon(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """説明文に英語の専門用語が含まれないこと。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        jargon = ["APY", "yield", "protocol", "leverage", "staking", "liquidity"]
        for term in jargon:
            assert term not in result.explanation, (
                f"Jargon '{term}' found in explanation: {result.explanation}"
            )

    @pytest.mark.asyncio
    async def test_all_amounts_are_decimal(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """全ての金額が Decimal 型であること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "balanced")
        for entry in result.allocations:
            assert isinstance(entry.allocation_pct, Decimal)
            assert isinstance(entry.amount_usd, Decimal)
            assert isinstance(entry.expected_apy, Decimal)
        assert isinstance(result.total_expected_apy, Decimal)
        assert isinstance(result.total_risk_score, Decimal)

    @pytest.mark.asyncio
    async def test_explanation_contains_disclaimer(
        self,
        allocator: PortfolioAllocator,
        ranked_results: list,
    ) -> None:
        """説明文に免責事項が含まれること。"""
        result = await allocator.allocate(ranked_results, Decimal("10000"), "conservative")
        assert "保証するものではありません" in result.explanation

    def test_pendle_yt_cap_is_enforced(
        self,
        allocator: PortfolioAllocator,
    ) -> None:
        """PENDLE_YT配分が10%を超えても制約後は10%以下になること。"""
        from app.ai.optimizer.schemas import AllocationEntry, Protocol

        allocations = [
            AllocationEntry(
                protocol=Protocol.AAVE,
                asset="USDC",
                allocation_pct=Decimal("45"),
                amount_usd=Decimal("4500"),
                expected_apy=Decimal("5"),
            ),
            AllocationEntry(
                protocol=Protocol.PENDLE_YT,
                asset="YT-stETH",
                allocation_pct=Decimal("50"),
                amount_usd=Decimal("5000"),
                expected_apy=Decimal("20"),
            ),
            AllocationEntry(
                protocol=Protocol.IDLE,
                asset="CASH",
                allocation_pct=Decimal("5"),
                amount_usd=Decimal("500"),
                expected_apy=Decimal("0"),
            ),
        ]
        constrained = allocator._apply_constraints(allocations)
        yt_entry = next((e for e in constrained if e.protocol == Protocol.PENDLE_YT), None)
        assert yt_entry is not None, "PENDLE_YT エントリが存在すること"
        assert yt_entry.allocation_pct <= Decimal("10"), (
            f"PENDLE_YT は 10% 以下のはずだが {yt_entry.allocation_pct}% になった"
        )
        # 合計が 100% になっていること
        total = sum(e.allocation_pct for e in constrained)
        assert abs(total - Decimal("100")) < Decimal("0.01"), (
            f"配分合計が 100% のはずだが {total}% になった"
        )
