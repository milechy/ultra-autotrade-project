# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""期待ネット利益計算モジュール。"""

from __future__ import annotations

import logging
from decimal import Decimal

from .schemas import NetBenefitResult, Recommendation, StrategyCandidate

logger = logging.getLogger(__name__)

# 推奨度判定の閾値
_STRONG_BUY_THRESHOLD = Decimal("0.5")  # net_benefit > gross_yield * 0.5 → STRONG_BUY


class ExpectedNetBenefitCalculator:
    """期待ネット利益計算クラス。

    Expected Net Benefit = Expected Revenue − Execution Cost − Risk Penalty
    全ての計算は Decimal で行う。float は使用しない。
    """

    def calculate(
        self,
        candidate: StrategyCandidate,
        investment_usd: Decimal,
        holding_days: int = 30,
    ) -> NetBenefitResult:
        """単一戦略のネット利益を計算する。

        計算式:
        gross_yield = investment_usd * (expected_apy / 100) * (holding_days / 365)
        total_cost = gas_cost_usd + bridge_cost_usd
        risk_penalty_amount = gross_yield * risk_penalty
        risk_adjusted_yield = gross_yield - risk_penalty_amount
        net_benefit = risk_adjusted_yield - total_cost

        推奨度ロジック:
        - net_benefit > gross_yield * 0.5 → STRONG_BUY
        - net_benefit > 0 → BUY
        - net_benefit > -total_cost → HOLD
        - else → AVOID
        """
        holding_days_decimal = Decimal(str(holding_days))

        # グロス利回り計算
        gross_yield = (
            investment_usd
            * (candidate.expected_apy / Decimal("100"))
            * (holding_days_decimal / Decimal("365"))
        )

        # 合計コスト計算
        total_cost = candidate.gas_cost_usd + candidate.bridge_cost_usd

        # リスク調整後利回り計算
        risk_penalty_amount = gross_yield * candidate.risk_penalty
        risk_adjusted_yield = gross_yield - risk_penalty_amount

        # ネット利益計算
        net_benefit = risk_adjusted_yield - total_cost

        # 推奨度判定
        recommendation = self._determine_recommendation(
            net_benefit=net_benefit,
            gross_yield=gross_yield,
            total_cost=total_cost,
        )

        logger.info(
            "NetBenefit[%s/%s]: gross=%.4f, cost=%.4f, risk_adj=%.4f, net=%.4f, rec=%s",
            candidate.protocol.value,
            candidate.asset,
            float(gross_yield),
            float(total_cost),
            float(risk_adjusted_yield),
            float(net_benefit),
            recommendation.value,
        )

        return NetBenefitResult(
            protocol=candidate.protocol,
            asset=candidate.asset,
            expected_net_benefit=net_benefit,
            gross_yield=gross_yield,
            total_cost=total_cost,
            risk_adjusted_yield=risk_adjusted_yield,
            expected_apy=candidate.expected_apy,
            rank=0,  # rank_strategies で設定
            recommendation=recommendation,
        )

    def _determine_recommendation(
        self,
        net_benefit: Decimal,
        gross_yield: Decimal,
        total_cost: Decimal,
    ) -> Recommendation:
        """推奨度を判定する。"""
        if net_benefit > gross_yield * _STRONG_BUY_THRESHOLD:
            return Recommendation.STRONG_BUY
        if net_benefit > Decimal("0"):
            return Recommendation.BUY
        if net_benefit > -total_cost:
            return Recommendation.HOLD
        return Recommendation.AVOID

    def rank_strategies(
        self,
        candidates: list[StrategyCandidate],
        investment_usd: Decimal,
        holding_days: int = 30,
    ) -> list[NetBenefitResult]:
        """全候補のネット利益を計算し、降順でソートしてランク付けする。

        ランクは 1 始まりで、ネット利益が高いほど良い（1 = 最良）。
        """
        results = [
            self.calculate(candidate, investment_usd, holding_days) for candidate in candidates
        ]

        # ネット利益降順でソート
        results.sort(key=lambda r: r.expected_net_benefit, reverse=True)

        # ランクを割り当て（1 始まり）
        ranked: list[NetBenefitResult] = []
        for i, result in enumerate(results, start=1):
            ranked.append(
                NetBenefitResult(
                    protocol=result.protocol,
                    asset=result.asset,
                    expected_net_benefit=result.expected_net_benefit,
                    gross_yield=result.gross_yield,
                    total_cost=result.total_cost,
                    risk_adjusted_yield=result.risk_adjusted_yield,
                    expected_apy=result.expected_apy,
                    rank=i,
                    recommendation=result.recommendation,
                )
            )

        logger.info(
            "rank_strategies: %d candidates ranked, best=%s net_benefit=%.4f",
            len(ranked),
            ranked[0].protocol.value if ranked else "none",
            float(ranked[0].expected_net_benefit) if ranked else 0.0,
        )

        return ranked
