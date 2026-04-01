"""AutoEvacuator のユニットテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.protocols.risk.auto_evacuate import AutoEvacuator
from app.protocols.risk.schemas import (
    CompoundRiskAssessment,
    EvacuationPlan,
    EvacuationResult,
    EvacuationStep,
    MaturityAlert,
    PegStatus,
    ProtocolHealth,
    RiskLevel,
)


def _make_protocol_health(risk_level: RiskLevel, protocol: str = "test") -> ProtocolHealth:
    return ProtocolHealth(
        protocol=protocol,
        risk_level=risk_level,
        tvl_usd=Decimal("1000000"),
        tvl_change_24h_pct=Decimal("0"),
        is_operational=True,
        last_checked=datetime.now(tz=timezone.utc),
        alerts=[],
    )


def _make_peg_status(risk_level: RiskLevel = RiskLevel.LOW) -> PegStatus:
    return PegStatus(
        current_ratio=Decimal("1.0"),
        deviation_pct=Decimal("0"),
        risk_level=risk_level,
        last_checked=datetime.now(tz=timezone.utc),
    )


def _make_maturity_alert(risk_level: RiskLevel = RiskLevel.MEDIUM) -> MaturityAlert:
    return MaturityAlert(
        market_address="0x" + "0" * 40,
        asset="stETH",
        maturity_date=datetime.now(tz=timezone.utc),
        days_remaining=10,
        risk_level=risk_level,
        action_required="monitor",
    )


def _make_assessment(
    should_evacuate: bool,
    overall_risk: RiskLevel = RiskLevel.CRITICAL,
    evacuation_reason: str = "テスト理由",
    include_maturity_alert: bool = True,
) -> CompoundRiskAssessment:
    return CompoundRiskAssessment(
        overall_risk=overall_risk,
        protocol_risks=[
            _make_protocol_health(RiskLevel.LOW, "aave"),
            _make_protocol_health(RiskLevel.LOW, "lido"),
            _make_protocol_health(RiskLevel.LOW, "pendle"),
        ],
        peg_status=_make_peg_status(),
        maturity_alerts=[_make_maturity_alert()] if include_maturity_alert else [],
        total_exposure_usd=Decimal("3000"),
        risk_score=Decimal("80"),
        recommendations=["緊急対応が必要です。"],
        should_evacuate=should_evacuate,
        evacuation_reason=evacuation_reason if should_evacuate else None,
    )


class TestCreateEvacuationPlan:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_evacuation_needed(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=False)
        result = await evacuator.create_evacuation_plan(assessment)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_plan_when_evacuation_needed(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        result = await evacuator.create_evacuation_plan(assessment)
        assert isinstance(result, EvacuationPlan)

    @pytest.mark.asyncio
    async def test_steps_ordered_yt_first(self, evacuator: AutoEvacuator) -> None:
        """YT リデーム（order=1）が最初に来る。"""
        assessment = _make_assessment(should_evacuate=True, include_maturity_alert=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert plan.steps[0].action == "redeem_yt"
        assert plan.steps[0].order == 1

    @pytest.mark.asyncio
    async def test_steps_include_pt_when_maturity_alert(self, evacuator: AutoEvacuator) -> None:
        """満期アラートがある場合、PT リデームが含まれる。"""
        assessment = _make_assessment(should_evacuate=True, include_maturity_alert=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        actions = [s.action for s in plan.steps]
        assert "redeem_pt" in actions

    @pytest.mark.asyncio
    async def test_steps_include_unstake_and_withdraw(self, evacuator: AutoEvacuator) -> None:
        """stETH unstake と Aave withdraw が含まれる。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        actions = [s.action for s in plan.steps]
        assert "unstake" in actions
        assert "withdraw" in actions

    @pytest.mark.asyncio
    async def test_all_destinations_are_usdc(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        for step in plan.steps:
            assert step.destination == "USDC"

    @pytest.mark.asyncio
    async def test_critical_risk_priority_is_immediate(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True, overall_risk=RiskLevel.CRITICAL)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert plan.priority == "immediate"

    @pytest.mark.asyncio
    async def test_high_risk_priority_is_within_1h(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True, overall_risk=RiskLevel.HIGH)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert plan.priority == "within_1h"

    @pytest.mark.asyncio
    async def test_medium_risk_priority_is_within_24h(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True, overall_risk=RiskLevel.MEDIUM)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert plan.priority == "within_24h"

    @pytest.mark.asyncio
    async def test_gas_cost_is_decimal(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert isinstance(plan.estimated_gas_cost_usd, Decimal)


class TestExecuteEvacuation:
    @pytest.mark.asyncio
    async def test_execute_dry_run_default(self, evacuator: AutoEvacuator) -> None:
        """デフォルトは dry_run=True。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan)
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_execute_returns_evacuation_result(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan, dry_run=True)
        assert isinstance(result, EvacuationResult)

    @pytest.mark.asyncio
    async def test_execute_dry_run_not_executed(self, evacuator: AutoEvacuator) -> None:
        """dry_run=True のとき executed=False。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan, dry_run=True)
        assert result.executed is False

    @pytest.mark.asyncio
    async def test_execute_steps_completed_matches(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan, dry_run=True)
        assert result.steps_completed == result.steps_total

    @pytest.mark.asyncio
    async def test_execute_errors_empty_on_success(self, evacuator: AutoEvacuator) -> None:
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan, dry_run=True)
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_execute_blocked_by_emergency_stop(self, evacuator: AutoEvacuator) -> None:
        """emergency_stop_active=True のとき実行がブロックされること。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(plan, emergency_stop_active=True)
        assert result.executed is False
        assert any("Emergency stop" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_execute_blocked_without_manual_approval(self, evacuator: AutoEvacuator) -> None:
        """dry_run=False, manual_approval=False, operation_mode="active" のとき実行がブロックされること。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(
            plan, dry_run=False, manual_approval=False, operation_mode="active"
        )
        assert result.executed is False
        assert any("Manual approval required" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_execute_allowed_managed_immediate(self, evacuator: AutoEvacuator) -> None:
        """dry_run=False, operation_mode="managed", plan.priority="immediate" のとき承認不要でブロックされないこと。"""
        # CRITICAL リスク → priority="immediate"
        assessment = _make_assessment(should_evacuate=True, overall_risk=RiskLevel.CRITICAL)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        assert plan.priority == "immediate"
        result = await evacuator.execute_evacuation(
            plan, dry_run=False, manual_approval=False, operation_mode="managed"
        )
        # PoC では未実装なので executed=False だが、承認エラーは含まれない
        assert result.executed is False
        assert not any("Manual approval required" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_execute_unimplemented_returns_false(self, evacuator: AutoEvacuator) -> None:
        """dry_run=False + 承認あり → executed=False（未実装のため）。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(
            plan, dry_run=False, manual_approval=True, operation_mode="active"
        )
        assert result.executed is False

    @pytest.mark.asyncio
    async def test_real_execution_returns_failure(self, evacuator: AutoEvacuator) -> None:
        """dry_run=False は未実装エラーを返すこと。"""
        assessment = _make_assessment(should_evacuate=True)
        plan = await evacuator.create_evacuation_plan(assessment)
        assert plan is not None
        result = await evacuator.execute_evacuation(
            plan, dry_run=False, manual_approval=True, operation_mode="active"
        )
        assert result.executed is False
        assert result.steps_completed == 0
        assert len(result.errors) > 0
        assert "not yet implemented" in result.errors[0]


class TestPrioritizeSteps:
    def test_prioritize_steps_sorts_ascending(self, evacuator: AutoEvacuator) -> None:
        steps = [
            EvacuationStep(
                protocol="aave",
                action="withdraw",
                asset="USDC",
                amount=Decimal("1000"),
                destination="USDC",
                order=4,
            ),
            EvacuationStep(
                protocol="pendle",
                action="redeem_yt",
                asset="YT-stETH",
                amount=Decimal("1000"),
                destination="USDC",
                order=1,
            ),
            EvacuationStep(
                protocol="lido",
                action="unstake",
                asset="stETH",
                amount=Decimal("1000"),
                destination="USDC",
                order=3,
            ),
        ]
        sorted_steps = evacuator._prioritize_steps(steps)
        orders = [s.order for s in sorted_steps]
        assert orders == sorted(orders)

    def test_prioritize_steps_yt_first(self, evacuator: AutoEvacuator) -> None:
        steps = [
            EvacuationStep(
                protocol="lido",
                action="unstake",
                asset="stETH",
                amount=Decimal("1000"),
                destination="USDC",
                order=3,
            ),
            EvacuationStep(
                protocol="pendle",
                action="redeem_yt",
                asset="YT-stETH",
                amount=Decimal("1000"),
                destination="USDC",
                order=1,
            ),
        ]
        sorted_steps = evacuator._prioritize_steps(steps)
        assert sorted_steps[0].order == 1
        assert sorted_steps[0].action == "redeem_yt"

    def test_all_amounts_are_decimal(self, evacuator: AutoEvacuator) -> None:
        """EvacuationStep の amount が Decimal 型であることを確認。"""
        steps = [
            EvacuationStep(
                protocol="aave",
                action="withdraw",
                asset="USDC",
                amount=Decimal("500"),
                destination="USDC",
                order=1,
            ),
        ]
        sorted_steps = evacuator._prioritize_steps(steps)
        assert isinstance(sorted_steps[0].amount, Decimal)
