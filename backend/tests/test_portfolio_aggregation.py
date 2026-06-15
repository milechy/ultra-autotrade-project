# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
tests/test_portfolio_aggregation.py

統合ポートフォリオ集約関数 (app.portfolio.aggregation) のユニットテスト。

テスト観点:
1. 3ソース全揃い: grand_total/allocation合計≈100/HF透過
2. 1ソース欠落 (wallet=None): degraded=True, sources_available=2
3. 全ソース 0 USD: allocation 全0, ゼロ除算なし
4. HF 無限大入力: 999.0 にキャップされること
5. available=False ソースが grand_total から除外されること
6. Decimal 精度: float 混入なし
7. aave_net_usd が wallet/cex と二重計上されないこと (独立性)
8. allocation_pct 合計が 100 になること (丸め誤差考慮)
"""

from decimal import Decimal

from app.portfolio.aggregation import aggregate_portfolio
from app.portfolio.aggregation_schemas import (
    SourceBalance,
    UnifiedPortfolioInput,
    UnifiedPortfolioView,
)

# ---------------------------------------------------------------------------
# ヘルパー: テスト用 SourceBalance 生成
# ---------------------------------------------------------------------------


def _aave(
    total_usd: str = "7000",
    supply_usd: str = "10000",
    borrow_usd: str = "3000",
    health_factor: str = "2.5",
    available: bool = True,
) -> SourceBalance:
    return SourceBalance(
        source="aave",
        total_usd=Decimal(total_usd),
        available=available,
        supply_usd=Decimal(supply_usd),
        borrow_usd=Decimal(borrow_usd),
        health_factor=Decimal(health_factor),
    )


def _wallet(
    total_usd: str = "2000",
    available: bool = True,
) -> SourceBalance:
    return SourceBalance(
        source="wallet",
        total_usd=Decimal(total_usd),
        available=available,
    )


def _cex(
    total_usd: str = "1000",
    available: bool = True,
) -> SourceBalance:
    return SourceBalance(
        source="cex",
        total_usd=Decimal(total_usd),
        available=available,
    )


# ---------------------------------------------------------------------------
# テストケース 1: 3ソース全揃い
# ---------------------------------------------------------------------------


class TestAllSourcesAvailable:
    def test_grand_total_correct(self) -> None:
        """aave(7000) + wallet(2000) + cex(1000) = 10000."""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.grand_total_usd == Decimal("10000")

    def test_individual_usds(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.aave_net_usd == Decimal("7000")
        assert result.wallet_usd == Decimal("2000")
        assert result.cex_usd == Decimal("1000")

    def test_health_factor_transparent(self) -> None:
        """HF は Aave ソースから透過される。"""
        inp = UnifiedPortfolioInput(aave=_aave(health_factor="2.5"), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.health_factor == Decimal("2.5")

    def test_not_degraded(self) -> None:
        """全ソース available=True なら degraded=False。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.degraded is False
        assert result.sources_available == 3
        assert result.sources_total == 3

    def test_allocation_pct_sum_approximately_100(self) -> None:
        """allocation_pct の合計が 100 に近いこと (丸め誤差 0.1 以内)。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        total_pct = sum(a.allocation_pct for a in result.allocations)
        assert abs(total_pct - Decimal("100")) <= Decimal("0.1")

    def test_allocation_values(self) -> None:
        """aave=70%, wallet=20%, cex=10%。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        alloc = {a.source: a.allocation_pct for a in result.allocations}
        assert alloc["aave"] == Decimal("70.00")
        assert alloc["wallet"] == Decimal("20.00")
        assert alloc["cex"] == Decimal("10.00")

    def test_all_allocations_available_true(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        for alloc in result.allocations:
            assert alloc.available is True

    def test_return_type(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert isinstance(result, UnifiedPortfolioView)


# ---------------------------------------------------------------------------
# テストケース 2: 1ソース欠落 (wallet=None)
# ---------------------------------------------------------------------------


class TestOneSourceMissing:
    def test_degraded_true(self) -> None:
        """wallet=None → degraded=True。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.degraded is True

    def test_sources_available_2(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.sources_available == 2

    def test_grand_total_excludes_missing_source(self) -> None:
        """wallet=None → grand_total は aave + cex のみ。"""
        inp = UnifiedPortfolioInput(aave=_aave("7000"), wallet=None, cex=_cex("1000"))
        result = aggregate_portfolio(inp)
        assert result.grand_total_usd == Decimal("8000")

    def test_wallet_usd_is_zero(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.wallet_usd == Decimal("0")

    def test_wallet_allocation_available_false(self) -> None:
        """欠落ソースの available は False として allocations に含まれる。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        wallet_alloc = next(a for a in result.allocations if a.source == "wallet")
        assert wallet_alloc.available is False
        assert wallet_alloc.total_usd == Decimal("0")

    def test_hf_still_present_if_aave_available(self) -> None:
        """Aave が available なら wallet 欠落でも HF は透過される。"""
        inp = UnifiedPortfolioInput(aave=_aave(health_factor="3.0"), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.health_factor == Decimal("3.0")

    def test_aave_missing_hf_is_none(self) -> None:
        """Aave が None なら HF は None。"""
        inp = UnifiedPortfolioInput(aave=None, wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert result.health_factor is None


# ---------------------------------------------------------------------------
# テストケース 3: 全ソース 0 USD / ゼロ除算なし
# ---------------------------------------------------------------------------


class TestAllZeroUsd:
    def test_no_zero_division_error(self) -> None:
        """全ソース 0 USD でもゼロ除算が発生しないこと。"""
        inp = UnifiedPortfolioInput(
            aave=_aave("0"),
            wallet=_wallet("0"),
            cex=_cex("0"),
        )
        result = aggregate_portfolio(inp)  # 例外なし
        assert result.grand_total_usd == Decimal("0")

    def test_all_allocation_pct_zero(self) -> None:
        """全 0 USD のとき allocation_pct は全て 0。"""
        inp = UnifiedPortfolioInput(
            aave=_aave("0"),
            wallet=_wallet("0"),
            cex=_cex("0"),
        )
        result = aggregate_portfolio(inp)
        for alloc in result.allocations:
            assert alloc.allocation_pct == Decimal("0")

    def test_not_degraded_when_all_zero_but_available(self) -> None:
        """全 0 USD でも available=True なら degraded=False。"""
        inp = UnifiedPortfolioInput(
            aave=_aave("0"),
            wallet=_wallet("0"),
            cex=_cex("0"),
        )
        result = aggregate_portfolio(inp)
        assert result.degraded is False
        assert result.sources_available == 3


# ---------------------------------------------------------------------------
# テストケース 4: HF 無限大入力
# ---------------------------------------------------------------------------


class TestHealthFactorInfinity:
    def test_hf_inf_capped_to_999(self) -> None:
        """Decimal('inf') は 999.0 にキャップされること。"""
        inp = UnifiedPortfolioInput(
            aave=_aave(health_factor="inf"),
            wallet=_wallet(),
            cex=_cex(),
        )
        result = aggregate_portfolio(inp)
        assert result.health_factor == Decimal("999.0")

    def test_hf_finite_not_capped(self) -> None:
        """有限 HF はそのまま透過される。"""
        inp = UnifiedPortfolioInput(
            aave=_aave(health_factor="1.8"),
            wallet=_wallet(),
            cex=_cex(),
        )
        result = aggregate_portfolio(inp)
        assert result.health_factor == Decimal("1.8")


# ---------------------------------------------------------------------------
# テストケース 5: available=False ソースが grand_total から除外されること
# ---------------------------------------------------------------------------


class TestSourceUnavailable:
    def test_unavailable_source_excluded_from_grand_total(self) -> None:
        """available=False のソースは grand_total に含まれない。"""
        inp = UnifiedPortfolioInput(
            aave=_aave("7000", available=True),
            wallet=_wallet("2000", available=False),  # fail-open フォールバック
            cex=_cex("1000", available=True),
        )
        result = aggregate_portfolio(inp)
        assert result.grand_total_usd == Decimal("8000")  # wallet 除外
        assert result.wallet_usd == Decimal("0")

    def test_unavailable_source_sets_degraded(self) -> None:
        """available=False のソースがあると degraded=True。"""
        inp = UnifiedPortfolioInput(
            aave=_aave(available=True),
            wallet=_wallet(available=False),
            cex=_cex(available=True),
        )
        result = aggregate_portfolio(inp)
        assert result.degraded is True
        assert result.sources_available == 2

    def test_unavailable_aave_hf_not_transparent(self) -> None:
        """Aave が available=False の場合、HF は None になる。"""
        inp = UnifiedPortfolioInput(
            aave=_aave(health_factor="2.5", available=False),
            wallet=_wallet(),
            cex=_cex(),
        )
        result = aggregate_portfolio(inp)
        assert result.health_factor is None

    def test_all_sources_unavailable(self) -> None:
        """全ソース available=False → grand_total=0, degraded=True, sources_available=0。"""
        inp = UnifiedPortfolioInput(
            aave=_aave(available=False),
            wallet=_wallet(available=False),
            cex=_cex(available=False),
        )
        result = aggregate_portfolio(inp)
        assert result.grand_total_usd == Decimal("0")
        assert result.degraded is True
        assert result.sources_available == 0


# ---------------------------------------------------------------------------
# テストケース 6: Decimal 精度 (float 混入チェック)
# ---------------------------------------------------------------------------


class TestDecimalPrecision:
    def test_grand_total_is_decimal(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert isinstance(result.grand_total_usd, Decimal)

    def test_allocation_pct_is_decimal(self) -> None:
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        for alloc in result.allocations:
            assert isinstance(alloc.allocation_pct, Decimal)

    def test_no_float_in_output(self) -> None:
        """出力に float 型の値が混入していないこと。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert isinstance(result.aave_net_usd, Decimal)
        assert isinstance(result.wallet_usd, Decimal)
        assert isinstance(result.cex_usd, Decimal)
        if result.health_factor is not None:
            assert isinstance(result.health_factor, Decimal)

    def test_allocation_pct_quantized_to_2dp(self) -> None:
        """allocation_pct は小数点以下2桁にquantize されること。"""
        inp = UnifiedPortfolioInput(
            aave=_aave("3333"),
            wallet=_wallet("3333"),
            cex=_cex("3334"),
        )
        result = aggregate_portfolio(inp)
        for alloc in result.allocations:
            # 小数点以下2桁以内であること
            assert alloc.allocation_pct == alloc.allocation_pct.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# テストケース 7: 二重計上なし (wallet と aave の独立性)
# ---------------------------------------------------------------------------


class TestNoDoubleCounting:
    def test_wallet_and_aave_are_independent(self) -> None:
        """wallet.total_usd と aave.total_usd は独立して合算される。

        wallet_balance_service.py L13 により wallet には Aave supply 分が含まれない。
        集約関数はそれぞれの total_usd をそのまま使用し、内部で減算・補正しない。
        """
        aave_src = _aave(total_usd="7000", supply_usd="10000", borrow_usd="3000")
        wallet_src = _wallet(total_usd="2000")
        cex_src = _cex(total_usd="1000")
        inp = UnifiedPortfolioInput(aave=aave_src, wallet=wallet_src, cex=cex_src)
        result = aggregate_portfolio(inp)
        # 合計は 7000 + 2000 + 1000 = 10000 (supply_usd=10000 は合算されない)
        assert result.grand_total_usd == Decimal("10000")
        assert result.aave_net_usd == Decimal("7000")
        assert result.wallet_usd == Decimal("2000")


# ---------------------------------------------------------------------------
# テストケース 8: allocations の長さとソース順序
# ---------------------------------------------------------------------------


class TestAllocationsStructure:
    def test_allocations_length_always_3(self) -> None:
        """欠落ソースがあっても allocations の長さは常に 3。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=None, cex=_cex())
        result = aggregate_portfolio(inp)
        assert len(result.allocations) == 3

    def test_allocations_source_order(self) -> None:
        """allocations のソース順序は aave → wallet → cex。"""
        inp = UnifiedPortfolioInput(aave=_aave(), wallet=_wallet(), cex=_cex())
        result = aggregate_portfolio(inp)
        assert [a.source for a in result.allocations] == ["aave", "wallet", "cex"]

    def test_all_sources_none(self) -> None:
        """全ソース None でも allocations は3要素 (全て available=False, usd=0)。"""
        inp = UnifiedPortfolioInput(aave=None, wallet=None, cex=None)
        result = aggregate_portfolio(inp)
        assert len(result.allocations) == 3
        assert result.grand_total_usd == Decimal("0")
        assert result.sources_available == 0
        assert result.degraded is True
        for alloc in result.allocations:
            assert alloc.available is False
            assert alloc.total_usd == Decimal("0")
            assert alloc.allocation_pct == Decimal("0")
