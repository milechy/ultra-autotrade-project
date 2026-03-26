# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""自動避難ロジックモジュール。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .schemas import (
    CompoundRiskAssessment,
    EvacuationPlan,
    EvacuationResult,
    EvacuationStep,
    RiskLevel,
)

logger = logging.getLogger(__name__)

# PoC: プロトコルごとのデフォルト推定エクスポージャー（USD）
_DEFAULT_POSITION_USD = Decimal("1000")

# ガスコスト見積もり（USD）
_GAS_COSTS: dict[str, Decimal] = {
    "pendle_yt": Decimal("15"),
    "pendle_pt": Decimal("12"),
    "lido": Decimal("10"),
    "aave": Decimal("8"),
}

# 優先度ごとの推定時間（分）
_TIME_ESTIMATES: dict[str, int] = {
    "immediate": 5,
    "within_1h": 30,
    "within_24h": 120,
}


class AutoEvacuator:
    """リスク軽減のための自動避難ロジック。"""

    def __init__(self) -> None:
        """初期化。外部依存なし（純粋ロジック）。"""
        pass

    async def create_evacuation_plan(
        self, assessment: CompoundRiskAssessment
    ) -> Optional[EvacuationPlan]:
        """避難計画を作成する。

        assessment.should_evacuate が False の場合は None を返す。

        避難順序（最高リスクから順に）:
        1. Pendle YT → redeem_yt（最高リスク）
        2. Pendle PT → redeem_pt（満期アラートがある場合）
        3. Lido stETH → unstake
        4. Aave → withdraw

        Args:
            assessment: 複合リスク評価結果。

        Returns:
            EvacuationPlan または None（避難不要の場合）。
        """
        if not assessment.should_evacuate:
            logger.info("create_evacuation_plan: 避難不要 → None を返します")
            return None

        logger.warning(
            "create_evacuation_plan: 避難計画作成開始（reason=%s）",
            assessment.evacuation_reason,
        )

        steps: list[EvacuationStep] = []

        # ステップ 1: Pendle YT（最高リスク）
        steps.append(
            EvacuationStep(
                protocol="pendle",
                action="redeem_yt",
                asset="YT-stETH",
                amount=_DEFAULT_POSITION_USD,
                destination="USDC",
                order=1,
            )
        )

        # ステップ 2: Pendle PT（満期アラートがある場合）
        if assessment.maturity_alerts:
            steps.append(
                EvacuationStep(
                    protocol="pendle",
                    action="redeem_pt",
                    asset="PT-stETH",
                    amount=_DEFAULT_POSITION_USD,
                    destination="USDC",
                    order=2,
                )
            )

        # ステップ 3: Lido stETH
        steps.append(
            EvacuationStep(
                protocol="lido",
                action="unstake",
                asset="stETH",
                amount=_DEFAULT_POSITION_USD,
                destination="USDC",
                order=3,
            )
        )

        # ステップ 4: Aave
        steps.append(
            EvacuationStep(
                protocol="aave",
                action="withdraw",
                asset="USDC",
                amount=_DEFAULT_POSITION_USD,
                destination="USDC",
                order=4,
            )
        )

        # 優先度決定
        priority = self._determine_priority(assessment.overall_risk)

        # ガスコスト合計
        estimated_gas = _GAS_COSTS["pendle_yt"]
        if assessment.maturity_alerts:
            estimated_gas += _GAS_COSTS["pendle_pt"]
        estimated_gas += _GAS_COSTS["lido"]
        estimated_gas += _GAS_COSTS["aave"]

        estimated_time = _TIME_ESTIMATES[priority]

        sorted_steps = self._prioritize_steps(steps)

        plan = EvacuationPlan(
            trigger_reason=assessment.evacuation_reason or "リスクスコアが危険域に達しました",
            steps=sorted_steps,
            estimated_gas_cost_usd=estimated_gas,
            estimated_time_minutes=estimated_time,
            priority=priority,
        )

        logger.warning(
            "避難計画作成完了: %d ステップ, priority=%s, gas=$%s",
            len(sorted_steps),
            priority,
            estimated_gas,
        )
        return plan

    async def execute_evacuation(
        self, plan: EvacuationPlan, dry_run: bool = True
    ) -> EvacuationResult:
        """避難計画を実行する。

        ⚠️ dry_run のデフォルトは True（明示的なオーバーライドなしに自動実行しない）

        PoC では常にシミュレーション成功を返す。
        本番実装ではプロトコルクライアントを順番に呼び出す。

        Args:
            plan: 実行する避難計画。
            dry_run: True の場合はシミュレーションのみ（デフォルト True）。

        Returns:
            EvacuationResult
        """
        logger.warning(
            "execute_evacuation: dry_run=%s, steps=%d",
            dry_run,
            len(plan.steps),
        )

        errors: list[str] = []
        steps_completed = 0

        if dry_run:
            # PoC: シミュレーション成功
            for step in plan.steps:
                logger.info(
                    "  [DRY RUN] ステップ %d: %s %s %s → %s",
                    step.order,
                    step.protocol,
                    step.action,
                    step.asset,
                    step.destination,
                )
            steps_completed = len(plan.steps)
        else:
            # PoC: 実装は未対応（本番フェーズで実装）
            logger.warning("execute_evacuation: 本番実行は未実装のため dry_run として扱います")
            steps_completed = len(plan.steps)

        return EvacuationResult(
            plan=plan,
            executed=not dry_run,
            dry_run=dry_run,
            steps_completed=steps_completed,
            steps_total=len(plan.steps),
            errors=errors,
        )

    def _prioritize_steps(self, steps: list[EvacuationStep]) -> list[EvacuationStep]:
        """ステップを order 昇順（最高リスク優先）でソートする。

        Args:
            steps: EvacuationStep のリスト。

        Returns:
            order 昇順にソートされたリスト。
        """
        return sorted(steps, key=lambda s: s.order)

    def _determine_priority(self, overall_risk: RiskLevel) -> str:
        """全体リスクレベルから優先度文字列を決定する。

        CRITICAL → "immediate"
        HIGH → "within_1h"
        その他 → "within_24h"
        """
        if overall_risk == RiskLevel.CRITICAL:
            return "immediate"
        if overall_risk == RiskLevel.HIGH:
            return "within_1h"
        return "within_24h"
