"""P0 安全装置配線テスト: AutoEvacuator + CompoundRiskAssessor が実際に呼ばれることを確認する。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.protocols.risk.schemas import (
    CompoundRiskAssessment,
    MaturityAlert,
    PegStatus,
    ProtocolHealth,
    RiskLevel,
)


def _make_protocol_health(risk_level: RiskLevel = RiskLevel.LOW) -> ProtocolHealth:
    return ProtocolHealth(
        protocol="aave",
        risk_level=risk_level,
        tvl_usd=Decimal("1000000"),
        tvl_change_24h_pct=Decimal("0"),
        is_operational=True,
        last_checked=datetime.now(tz=timezone.utc),
        alerts=[],
    )


def _make_assessment(should_evacuate: bool, risk_level: RiskLevel = RiskLevel.LOW) -> CompoundRiskAssessment:
    peg = PegStatus(
        current_ratio=Decimal("0.9998"),
        deviation_pct=Decimal("0.02"),
        risk_level=RiskLevel.LOW,
        last_checked=datetime.now(tz=timezone.utc),
    )
    score = Decimal("80") if should_evacuate else Decimal("10")
    return CompoundRiskAssessment(
        overall_risk=risk_level,
        protocol_risks=[_make_protocol_health(risk_level)],
        peg_status=peg,
        maturity_alerts=[],
        total_exposure_usd=Decimal("1000"),
        risk_score=score,
        recommendations=["test"],
        should_evacuate=should_evacuate,
        evacuation_reason="テスト理由" if should_evacuate else None,
    )


# ---------------------------------------------------------------------------
# compound_risk_monitor_loop の配線テスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compound_risk_monitor_loop_calls_assessor_and_evacuator() -> None:
    """compound_risk_monitor_loop が CompoundRiskAssessor + AutoEvacuator を呼ぶことを確認。"""
    from app.automation.scheduled_tasks import compound_risk_monitor_loop
    from app.protocols.risk.schemas import EvacuationPlan, EvacuationResult, EvacuationStep

    assessment = _make_assessment(should_evacuate=True, risk_level=RiskLevel.CRITICAL)

    plan = EvacuationPlan(
        trigger_reason="テスト",
        steps=[
            EvacuationStep(
                protocol="aave",
                action="withdraw",
                asset="USDC",
                amount=Decimal("1000"),
                destination="USDC",
                order=1,
            )
        ],
        estimated_gas_cost_usd=Decimal("8"),
        estimated_time_minutes=5,
        priority="immediate",
    )
    evac_result = EvacuationResult(
        plan=plan,
        executed=False,
        dry_run=True,
        steps_completed=1,
        steps_total=1,
        errors=[],
    )

    mock_assessor = MagicMock()
    mock_assessor.assess = AsyncMock(return_value=assessment)
    mock_evacuator = MagicMock()
    mock_evacuator.create_evacuation_plan = AsyncMock(return_value=plan)
    mock_evacuator.execute_evacuation = AsyncMock(return_value=evac_result)

    # Local imports inside the loop function → patch at source module level
    with (
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor", return_value=mock_assessor),
        patch("app.protocols.risk.auto_evacuate.AutoEvacuator", return_value=mock_evacuator),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await compound_risk_monitor_loop(interval_seconds=1)

    mock_assessor.assess.assert_called_once()
    mock_evacuator.create_evacuation_plan.assert_called_once_with(assessment)
    mock_evacuator.execute_evacuation.assert_called_once()
    _, kwargs = mock_evacuator.execute_evacuation.call_args
    assert kwargs.get("dry_run", True) is True


@pytest.mark.asyncio
async def test_compound_risk_monitor_loop_no_evacuate_skips_evacuator() -> None:
    """should_evacuate=False の場合 AutoEvacuator は呼ばれない。"""
    from app.automation.scheduled_tasks import compound_risk_monitor_loop

    assessment = _make_assessment(should_evacuate=False)

    mock_assessor = MagicMock()
    mock_assessor.assess = AsyncMock(return_value=assessment)
    mock_evacuator = MagicMock()
    mock_evacuator.create_evacuation_plan = AsyncMock(return_value=None)

    with (
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor", return_value=mock_assessor),
        patch("app.protocols.risk.auto_evacuate.AutoEvacuator", return_value=mock_evacuator),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await compound_risk_monitor_loop(interval_seconds=1)

    mock_assessor.assess.assert_called_once()
    mock_evacuator.create_evacuation_plan.assert_not_called()


# ---------------------------------------------------------------------------
# ScheduledTaskManager の compound_risk 配線テスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_task_manager_start_stop_compound_risk() -> None:
    """ScheduledTaskManager が compound_risk_monitor を start/stop できる。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()
    assert not manager.is_compound_risk_running

    with patch("app.automation.scheduled_tasks.compound_risk_monitor_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = None
        await manager.start_compound_risk_monitor(interval_seconds=600)
        assert manager.is_compound_risk_running

        await manager.stop_compound_risk_monitor()
        assert not manager.is_compound_risk_running


# ---------------------------------------------------------------------------
# workflow.py の CompoundRiskAssessor pre-check 配線テスト
# ---------------------------------------------------------------------------


def test_workflow_blocks_on_compound_risk_should_evacuate() -> None:
    """workflow.py が CompoundRiskAssessor.should_evacuate=True で HOLD を返す。"""
    from app.automation.workflow import process_pending_knowledge

    assessment = _make_assessment(should_evacuate=True, risk_level=RiskLevel.CRITICAL)

    mock_db = MagicMock()
    mock_ks = MagicMock()
    mock_as = MagicMock()
    mock_es = MagicMock()

    mock_pending = [MagicMock(id=1), MagicMock(id=2)]
    mock_ks.get_pending.return_value = mock_pending

    mock_assessor = MagicMock()
    mock_assessor.assess = AsyncMock(return_value=assessment)

    mock_future = MagicMock()
    mock_future.result.return_value = assessment
    mock_pool = MagicMock()
    mock_pool.__enter__ = MagicMock(return_value=mock_pool)
    mock_pool.__exit__ = MagicMock(return_value=False)
    mock_pool.submit.return_value = mock_future

    with (
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor", return_value=mock_assessor),
        patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_pool),
    ):
        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_as,
            exchange_service=mock_es,
        )

    assert result.hold_count == len(mock_pending)
    assert result.status == "completed"


def test_workflow_continues_when_compound_risk_not_evacuate() -> None:
    """workflow.py が CompoundRiskAssessor.should_evacuate=False で処理を継続する。"""
    from app.automation.workflow import process_pending_knowledge

    assessment = _make_assessment(should_evacuate=False)

    mock_db = MagicMock()
    mock_ks = MagicMock()
    mock_as = MagicMock()
    mock_es = MagicMock()

    mock_ks.get_pending.return_value = []

    mock_assessor = MagicMock()
    mock_assessor.assess = AsyncMock(return_value=assessment)

    mock_future = MagicMock()
    mock_future.result.return_value = assessment
    mock_pool = MagicMock()
    mock_pool.__enter__ = MagicMock(return_value=mock_pool)
    mock_pool.__exit__ = MagicMock(return_value=False)
    mock_pool.submit.return_value = mock_future

    with (
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor", return_value=mock_assessor),
        patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_pool),
    ):
        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_as,
            exchange_service=mock_es,
        )

    # pending=[] なので CompoundRisk チェックは通過して no_items が返る
    assert result.status == "no_items"


def test_workflow_fail_open_on_compound_risk_exception() -> None:
    """compound_risk チェックが例外を投げても workflow は続行する（fail-open）。"""
    from app.automation.workflow import process_pending_knowledge

    mock_db = MagicMock()
    mock_ks = MagicMock()
    mock_as = MagicMock()
    mock_es = MagicMock()

    mock_ks.get_pending.return_value = []

    with patch("app.protocols.risk.compound_risk.CompoundRiskAssessor", side_effect=RuntimeError("test error")):
        result = process_pending_knowledge(
            mock_db,
            knowledge_service=mock_ks,
            ai_service=mock_as,
            exchange_service=mock_es,
        )

    assert result.status == "no_items"
