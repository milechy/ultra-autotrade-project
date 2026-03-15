"""Tests for StressController."""

from __future__ import annotations

import pytest

from app.aave.schemas import AaveOperationMode
from app.automation.stress_controller import (
    MarketStressData,
    StressController,
)


@pytest.fixture
def controller() -> StressController:
    return StressController()


def normal_data(**kwargs) -> MarketStressData:
    defaults = dict(
        price_change_24h=0.0,
        health_factor=2.0,
        manual_stop=False,
        current_mode=AaveOperationMode.NORMAL,
        current_stage=0,
    )
    defaults.update(kwargs)
    return MarketStressData(**defaults)


def test_stage0_normal(controller: StressController) -> None:
    result = controller.evaluate(normal_data(price_change_24h=0.0))
    assert result.stage == 0
    assert result.action == "normal"
    assert result.mode == AaveOperationMode.NORMAL


def test_stage1_trigger(controller: StressController) -> None:
    result = controller.evaluate(normal_data(price_change_24h=-0.10))
    assert result.stage == 1
    assert result.action == "pause_deposit"
    assert result.mode == AaveOperationMode.SAFE_MODE


def test_stage1_boundary_just_below(controller: StressController) -> None:
    result = controller.evaluate(normal_data(price_change_24h=-0.11))
    assert result.stage == 1


def test_stage2_trigger(controller: StressController) -> None:
    result = controller.evaluate(normal_data(price_change_24h=-0.15))
    assert result.stage == 2
    assert result.action == "partial_withdraw"
    assert result.mode == AaveOperationMode.SAFE_MODE


def test_stage3_trigger(controller: StressController) -> None:
    result = controller.evaluate(normal_data(price_change_24h=-0.20))
    assert result.stage == 3
    assert result.action == "safe_asset_retreat"
    assert result.mode == AaveOperationMode.SAFE_MODE


def test_stage4_manual_stop(controller: StressController) -> None:
    result = controller.evaluate(normal_data(manual_stop=True))
    assert result.stage == 4
    assert result.action == "hard_stop"
    assert result.mode == AaveOperationMode.HARD_STOP


def test_stage4_low_health_factor(controller: StressController) -> None:
    result = controller.evaluate(normal_data(health_factor=1.5))
    assert result.stage == 4
    assert result.mode == AaveOperationMode.HARD_STOP


def test_stage4_or_logic_both(controller: StressController) -> None:
    """Stage 4 triggers when EITHER manual_stop=True OR HF < 1.6."""
    result = controller.evaluate(normal_data(manual_stop=True, health_factor=1.5))
    assert result.stage == 4
    assert "manual_stop=True" in result.reason
    assert "health_factor" in result.reason


def test_no_relaxation(controller: StressController) -> None:
    """Stage must not decrease: if current_stage=3, computed=1 → final=3."""
    result = controller.evaluate(normal_data(price_change_24h=-0.10, current_stage=3))
    assert result.stage == 3
    assert "no-relaxation" in result.reason


def test_withdraw_plan_stage2(controller: StressController) -> None:
    plan = controller.get_withdraw_plan(2)
    assert plan.stage == 2
    assert len(plan.steps) == 1
    assert plan.steps[0].asset_symbol == "USDC"
    assert plan.steps[0].amount == pytest.approx(0.25)
    assert plan.total_withdraw == pytest.approx(0.25)


def test_withdraw_plan_stage3(controller: StressController) -> None:
    plan = controller.get_withdraw_plan(3)
    assert plan.stage == 3
    assert len(plan.steps) == 2
    symbols = {s.asset_symbol for s in plan.steps}
    assert symbols == {"USDC", "USDT"}
    assert plan.total_withdraw == pytest.approx(1.0)


def test_withdraw_plan_stage4_noop(controller: StressController) -> None:
    plan = controller.get_withdraw_plan(4)
    assert plan.stage == 4
    assert len(plan.steps) == 0
    assert plan.total_withdraw == pytest.approx(0.0)
