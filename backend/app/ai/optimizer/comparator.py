# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""戦略比較レポート生成モジュール。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from .net_benefit import ExpectedNetBenefitCalculator
from .schemas import NetBenefitResult, StrategyComparison
from .strategy_scorer import StrategyScorer

logger = logging.getLogger(__name__)

# プロトコル表示名（日本語）
_PROTOCOL_DISPLAY: dict[str, str] = {
    "aave": "Aave 預金",
    "lido": "Lido ステーキング",
    "lido_aave": "Lido + Aave 複合",
    "pendle_pt": "Pendle 固定利回り",
    "pendle_yt": "Pendle レバレッジ",
    "idle": "未運用（現金）",
}

# 推奨度表示名（日本語）
_RECOMMENDATION_DISPLAY: dict[str, str] = {
    "STRONG_BUY": "強く推奨",
    "BUY": "推奨",
    "HOLD": "保留",
    "AVOID": "非推奨",
}


class StrategyComparator:
    """利用者透明性のための戦略比較レポートを生成するクラス。"""

    def __init__(
        self,
        scorer: Optional[StrategyScorer] = None,
        calculator: Optional[ExpectedNetBenefitCalculator] = None,
    ) -> None:
        self._scorer = scorer or StrategyScorer()
        self._calculator = calculator or ExpectedNetBenefitCalculator()

    def compare(
        self,
        investment_usd: Decimal,
        risk_mode: str = "conservative",
        holding_days: int = 30,
    ) -> StrategyComparison:
        """全プロトコルを比較して推奨を生成する。

        1. スコアラーから全候補を取得
        2. 各候補のネット利益を計算
        3. ランク付け
        4. idle_benefit（機会コスト = 0、何もしない場合の収益はゼロ）
        5. 推奨 = ランク 1 の結果
        6. comparison_timestamp = ISO 形式の UTC 文字列
        """
        candidates = self._scorer.get_all_candidates()
        ranked_results = self._calculator.rank_strategies(candidates, investment_usd, holding_days)

        # 何もしない場合の機会コスト = 0（現金は利回りなし）
        idle_benefit = Decimal("0")

        # 推奨 = ランク 1
        recommended = ranked_results[0]

        # タイムスタンプ（UTC ISO 形式）
        comparison_timestamp = datetime.now(UTC).isoformat()

        logger.info(
            "compare: investment=%s, holding=%dd, recommended=%s, net_benefit=%s",
            investment_usd,
            holding_days,
            recommended.protocol.value,
            recommended.expected_net_benefit,
        )

        return StrategyComparison(
            candidates=ranked_results,
            recommended=recommended,
            idle_benefit=idle_benefit,
            comparison_timestamp=comparison_timestamp,
        )

    def generate_report(
        self,
        comparison: StrategyComparison,
        risk_mode: str = "conservative",
    ) -> str:
        """人間が読みやすいレポートテキストを生成する（日本語）。

        専門用語なし。わかりやすい言葉で。
        """
        recommended = comparison.recommended
        protocol_name = _PROTOCOL_DISPLAY.get(
            recommended.protocol.value, recommended.protocol.value
        )
        rec_name = _RECOMMENDATION_DISPLAY.get(
            recommended.recommendation.value, recommended.recommendation.value
        )

        # ランキング行を生成
        ranking_lines: list[str] = []
        for result in comparison.candidates:
            pname = _PROTOCOL_DISPLAY.get(result.protocol.value, result.protocol.value)
            rname = _RECOMMENDATION_DISPLAY.get(
                result.recommendation.value, result.recommendation.value
            )
            benefit_val = float(result.expected_net_benefit)
            ranking_lines.append(f"{result.rank}. {pname}: 期待利益 ${benefit_val:.2f} ({rname})")

        ranking_text = "\n".join(ranking_lines)

        # 推奨プロトコルの詳細
        net_benefit_val = float(recommended.expected_net_benefit)
        idle_cost = float(comparison.idle_benefit)

        # 保有日数（利益から逆算は難しいため省略表示）
        report = f"""=== 戦略比較レポート ===
リスクモード: {risk_mode}

【推奨】{protocol_name}: 期待利益 ${net_benefit_val:.2f} ({rec_name})

--- 全戦略ランキング ---
{ranking_text}

何もしない場合の機会コスト: ${idle_cost:.2f}"""

        logger.info(
            "generate_report: recommended=%s, net_benefit=%.4f",
            recommended.protocol.value,
            net_benefit_val,
        )

        return report

    def _format_result(self, result: NetBenefitResult) -> str:
        """単一結果を人間が読みやすい文字列に変換する。"""
        protocol_name = _PROTOCOL_DISPLAY.get(result.protocol.value, result.protocol.value)
        rec_name = _RECOMMENDATION_DISPLAY.get(
            result.recommendation.value, result.recommendation.value
        )
        return (
            f"{result.rank}. {protocol_name} ({result.asset}): "
            f"期待利益 ${float(result.expected_net_benefit):.2f}, {rec_name}"
        )
