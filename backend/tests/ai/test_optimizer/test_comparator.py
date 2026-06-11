# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""StrategyComparator のテスト。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.optimizer.comparator import StrategyComparator
from app.ai.optimizer.net_benefit import ExpectedNetBenefitCalculator
from app.ai.optimizer.schemas import StrategyComparison
from app.ai.optimizer.strategy_scorer import StrategyScorer


@pytest.fixture
def comparator() -> StrategyComparator:
    """StrategyComparator インスタンス。"""
    return StrategyComparator()


class TestCompare:
    """compare メソッドのテスト。"""

    def test_compare_returns_all_candidates(self, comparator: StrategyComparator) -> None:
        """compare が全候補を含む StrategyComparison を返すこと。"""
        result = comparator.compare(Decimal("10000"))
        # 全5プロトコルが含まれること
        assert len(result.candidates) == 5

    def test_compare_recommended_is_rank_1(self, comparator: StrategyComparator) -> None:
        """compare の推奨がランク 1 であること。"""
        result = comparator.compare(Decimal("10000"))
        assert result.recommended.rank == 1

    def test_compare_recommended_has_highest_net_benefit(
        self, comparator: StrategyComparator
    ) -> None:
        """compare の推奨が最高のネット利益を持つこと。"""
        result = comparator.compare(Decimal("10000"))
        for candidate in result.candidates:
            assert result.recommended.expected_net_benefit >= candidate.expected_net_benefit

    def test_compare_idle_benefit_is_zero(self, comparator: StrategyComparator) -> None:
        """現金の機会コストがゼロであること（現金は利回りなし）。"""
        result = comparator.compare(Decimal("10000"))
        assert result.idle_benefit == Decimal("0")

    def test_compare_idle_benefit_is_decimal(self, comparator: StrategyComparator) -> None:
        """idle_benefit が Decimal 型であること。"""
        result = comparator.compare(Decimal("10000"))
        assert isinstance(result.idle_benefit, Decimal)

    def test_compare_timestamp_is_iso_format(self, comparator: StrategyComparator) -> None:
        """comparison_timestamp が ISO 形式であること。"""
        from datetime import datetime

        result = comparator.compare(Decimal("10000"))
        # ISO 形式のパースが成功することを確認
        try:
            datetime.fromisoformat(result.comparison_timestamp)
        except ValueError:
            pytest.fail(f"comparison_timestamp is not ISO format: {result.comparison_timestamp}")

    def test_compare_all_net_benefits_are_decimal(self, comparator: StrategyComparator) -> None:
        """全てのネット利益が Decimal 型であること。"""
        result = comparator.compare(Decimal("10000"))
        for candidate in result.candidates:
            assert isinstance(candidate.expected_net_benefit, Decimal)
            assert isinstance(candidate.gross_yield, Decimal)
            assert isinstance(candidate.risk_adjusted_yield, Decimal)


class TestGenerateReport:
    """generate_report メソッドのテスト。"""

    def test_generate_report_returns_non_empty_string(self, comparator: StrategyComparator) -> None:
        """generate_report が空でない文字列を返すこと。"""
        comparison = comparator.compare(Decimal("10000"))
        report = comparator.generate_report(comparison)
        assert report
        assert len(report) > 0

    def test_generate_report_contains_title(self, comparator: StrategyComparator) -> None:
        """generate_report が '戦略比較レポート' を含むこと。"""
        comparison = comparator.compare(Decimal("10000"))
        report = comparator.generate_report(comparison)
        assert "戦略比較レポート" in report

    def test_generate_report_contains_recommended_protocol_info(
        self, comparator: StrategyComparator
    ) -> None:
        """generate_report が推奨プロトコルの情報を含むこと。"""
        comparison = comparator.compare(Decimal("10000"))
        report = comparator.generate_report(comparison)
        # 推奨 または ランキングが含まれること
        assert "推奨" in report

    def test_generate_report_contains_ranking_section(self, comparator: StrategyComparator) -> None:
        """generate_report がランキングセクションを含むこと。"""
        comparison = comparator.compare(Decimal("10000"))
        report = comparator.generate_report(comparison)
        assert "ランキング" in report

    def test_comparator_uses_custom_scorer_and_calculator(self) -> None:
        """カスタムスコアラーとカリキュレーターを使用できること。"""
        scorer = StrategyScorer()
        calc = ExpectedNetBenefitCalculator()
        comparator = StrategyComparator(scorer=scorer, calculator=calc)
        result = comparator.compare(Decimal("5000"))
        assert result is not None
        assert len(result.candidates) == 5

    def test_report_contains_disclaimer(self, comparator: StrategyComparator) -> None:
        """generate_report が免責事項を含むこと。"""
        comparison = comparator.compare(Decimal("10000"))
        report = comparator.generate_report(comparison)
        assert "保証するものではありません" in report


class TestRiskModePropagation:
    """compare(risk_mode=...) が scorer のリスク重みへ伝播することの検証（レビュー M1）。

    risk_penalty が大きいほど risk_adjusted_yield / net_benefit は小さくなる
    （net_benefit.py: risk_adjusted_yield = gross_yield * (1 - risk_penalty)）。
    conservative(×1.5) > balanced(×1.0) > aggressive(×0.7) のリスクペナルティ重みが
    実際にランキング数値へ反映されることを、同一プロトコルの数値比較で担保する。
    """

    @staticmethod
    def _net_benefit_by_protocol(comparison: StrategyComparison) -> dict[str, Decimal]:
        return {r.protocol.value: r.expected_net_benefit for r in comparison.candidates}

    def test_compare_risk_mode_changes_net_benefit(self, comparator: StrategyComparator) -> None:
        """同一 comparator で risk_mode を変えると net_benefit が変わること。

        既定スコアラー（balanced）を注入した comparator でも、compare() が
        risk_mode に応じた scorer を生成し直すため数値が変わる。
        """
        conservative = self._net_benefit_by_protocol(
            comparator.compare(Decimal("10000"), risk_mode="conservative")
        )
        aggressive = self._net_benefit_by_protocol(
            comparator.compare(Decimal("10000"), risk_mode="aggressive")
        )

        # リスクのあるプロトコルでは conservative(高ペナルティ) < aggressive(低ペナルティ)
        for protocol in ("lido", "lido_aave", "pendle_pt", "pendle_yt"):
            assert conservative[protocol] < aggressive[protocol], (
                f"{protocol}: conservative={conservative[protocol]} は "
                f"aggressive={aggressive[protocol]} より小さいはず"
            )

    def test_compare_conservative_balanced_aggressive_ordering(
        self, comparator: StrategyComparator
    ) -> None:
        """pendle_yt（最高リスク）で conservative < balanced < aggressive の単調性。"""
        c = self._net_benefit_by_protocol(
            comparator.compare(Decimal("10000"), risk_mode="conservative")
        )["pendle_yt"]
        b = self._net_benefit_by_protocol(
            comparator.compare(Decimal("10000"), risk_mode="balanced")
        )["pendle_yt"]
        a = self._net_benefit_by_protocol(
            comparator.compare(Decimal("10000"), risk_mode="aggressive")
        )["pendle_yt"]
        assert c < b < a

    def test_compare_results_are_decimal(self, comparator: StrategyComparator) -> None:
        """risk_mode を変えても net_benefit は Decimal 型を維持すること。"""
        result = comparator.compare(Decimal("10000"), risk_mode="aggressive")
        for candidate in result.candidates:
            assert isinstance(candidate.expected_net_benefit, Decimal)

    def test_compare_default_scorer_risk_mode_reused(self) -> None:
        """注入スコアラーの risk_mode と一致する場合は同一インスタンスを再利用すること。"""
        scorer = StrategyScorer(risk_mode="aggressive")
        comparator = StrategyComparator(scorer=scorer)
        # 同じ risk_mode → 同一インスタンスが使われる（再生成しない）
        assert comparator._scorer_for_risk_mode("aggressive") is scorer
        # 異なる risk_mode → 新規生成
        regenerated = comparator._scorer_for_risk_mode("conservative")
        assert regenerated is not scorer
        assert regenerated._risk_mode == "conservative"
