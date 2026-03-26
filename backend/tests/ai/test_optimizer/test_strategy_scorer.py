# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""StrategyScorer のテスト。"""

from __future__ import annotations

from decimal import Decimal

from app.ai.optimizer.schemas import Protocol
from app.ai.optimizer.strategy_scorer import StrategyScorer


class TestStrategyScorer:
    """StrategyScorer の各メソッドのテスト。"""

    def test_score_aave_returns_aave_protocol(self, scorer: StrategyScorer) -> None:
        """score_aave が AAVE プロトコルを返すこと。"""
        result = scorer.score_aave()
        assert result.protocol == Protocol.AAVE

    def test_score_aave_returns_correct_apy(self, scorer: StrategyScorer) -> None:
        """score_aave が正しい APY を返すこと。"""
        result = scorer.score_aave()
        assert result.expected_apy == Decimal("4.5")

    def test_score_lido_returns_lido_protocol(self, scorer: StrategyScorer) -> None:
        """score_lido が LIDO プロトコルを返すこと。"""
        result = scorer.score_lido()
        assert result.protocol == Protocol.LIDO

    def test_score_lido_aave_returns_lido_aave_protocol(self, scorer: StrategyScorer) -> None:
        """score_lido_aave が LIDO_AAVE プロトコルを返すこと。"""
        result = scorer.score_lido_aave()
        assert result.protocol == Protocol.LIDO_AAVE

    def test_score_lido_aave_compound_apy(self, scorer: StrategyScorer) -> None:
        """score_lido_aave の APY が Lido + Aave stETH の合計であること（3.5 + 1.5 = 5.0）。"""
        result = scorer.score_lido_aave()
        expected = Decimal("3.5") + Decimal("1.5")
        assert result.expected_apy == expected

    def test_score_pendle_pt_returns_pendle_pt_protocol(self, scorer: StrategyScorer) -> None:
        """score_pendle_pt が PENDLE_PT プロトコルを返すこと。"""
        result = scorer.score_pendle_pt()
        assert result.protocol == Protocol.PENDLE_PT

    def test_score_pendle_pt_returns_implied_apy(self, scorer: StrategyScorer) -> None:
        """score_pendle_pt が implied APY を返すこと。"""
        result = scorer.score_pendle_pt()
        assert result.expected_apy == Decimal("5.2")

    def test_score_pendle_yt_returns_pendle_yt_protocol(self, scorer: StrategyScorer) -> None:
        """score_pendle_yt が PENDLE_YT プロトコルを返すこと。"""
        result = scorer.score_pendle_yt()
        assert result.protocol == Protocol.PENDLE_YT

    def test_score_pendle_yt_high_risk_penalty(self, scorer: StrategyScorer) -> None:
        """score_pendle_yt のリスクペナルティが 0.30（高リスク）であること。"""
        result = scorer.score_pendle_yt()
        assert result.risk_penalty == Decimal("0.30")

    def test_get_all_candidates_returns_exactly_5(self, scorer: StrategyScorer) -> None:
        """get_all_candidates が正確に 5 候補を返すこと。"""
        candidates = scorer.get_all_candidates()
        assert len(candidates) == 5

    def test_get_all_candidates_contains_all_protocols(self, scorer: StrategyScorer) -> None:
        """get_all_candidates が全プロトコルを含むこと。"""
        candidates = scorer.get_all_candidates()
        protocols = {c.protocol for c in candidates}
        expected = {
            Protocol.AAVE,
            Protocol.LIDO,
            Protocol.LIDO_AAVE,
            Protocol.PENDLE_PT,
            Protocol.PENDLE_YT,
        }
        assert protocols == expected

    def test_all_apy_values_are_decimal(self, scorer: StrategyScorer) -> None:
        """全ての APY 値が Decimal 型であること。"""
        candidates = scorer.get_all_candidates()
        for c in candidates:
            assert isinstance(c.expected_apy, Decimal), f"{c.protocol}: expected_apy is not Decimal"

    def test_all_gas_costs_are_decimal(self, scorer: StrategyScorer) -> None:
        """全てのガスコストが Decimal 型であること。"""
        candidates = scorer.get_all_candidates()
        for c in candidates:
            assert isinstance(c.gas_cost_usd, Decimal), f"{c.protocol}: gas_cost_usd is not Decimal"

    def test_risk_penalties_in_valid_range(self, scorer: StrategyScorer) -> None:
        """全てのリスクペナルティが 0-1 の範囲内であること。"""
        candidates = scorer.get_all_candidates()
        for c in candidates:
            assert Decimal("0") <= c.risk_penalty <= Decimal("1"), (
                f"{c.protocol}: risk_penalty={c.risk_penalty} is out of range"
            )

    def test_pendle_maturity_days_is_set(self, scorer: StrategyScorer) -> None:
        """Pendle 候補に maturity_days が設定されていること。"""
        pt = scorer.score_pendle_pt()
        yt = scorer.score_pendle_yt()
        assert pt.maturity_days is not None
        assert yt.maturity_days is not None
        assert pt.maturity_days == 30
        assert yt.maturity_days == 30
