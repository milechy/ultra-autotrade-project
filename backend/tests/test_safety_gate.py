# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_safety_gate.py
"""safety_gate.evaluate_hard_stop の単体テスト（Phase 0 / スライス0-E1）。

経路非依存の HARD_STOP 純関数が、CEX 経路と同一の判定順・fail-closed/open
セマンティクスを返すことを検証する（副作用なし）。
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.automation.safety_gate import HardStopResult, evaluate_hard_stop


def test_rule_engine_block_returns_first() -> None:
    """rule engine が止めたら source=rule_engine で即 blocked。"""
    with patch(
        "app.automation.workflow.check_rule_engine",
        return_value=(False, "hf_below_threshold"),
    ):
        r = evaluate_hard_stop(MagicMock(), Decimal("1.5"), run_compound_risk=False)
    assert r.blocked
    assert r.source == "rule_engine"
    assert r.reason == "hf_below_threshold"


def test_all_clear_not_blocked() -> None:
    """全チェック通過なら blocked=False。"""
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.return_value = MagicMock(active=False, reason="")
        # monitoring_service=None で StressController をスキップ、compound もスキップ
        r = evaluate_hard_stop(None, None, run_compound_risk=False)
    assert r == HardStopResult(blocked=False)


def test_macro_active_blocks() -> None:
    """MacroSafeMode active なら source=macro で blocked。"""
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.return_value = MagicMock(
            active=True, reason="FOMC window"
        )
        r = evaluate_hard_stop(None, None, run_compound_risk=False)
    assert r.blocked
    assert r.source == "macro"
    assert r.reason == "FOMC window"


def test_macro_eval_failure_is_fail_closed() -> None:
    """MacroSafeMode 評価失敗は fail-closed（blocked）。"""
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.side_effect = RuntimeError("boom")
        r = evaluate_hard_stop(None, None, run_compound_risk=False)
    assert r.blocked
    assert r.source == "macro"
    assert r.reason == "macro_safe_mode_eval_failed"


def test_compound_evacuate_blocks() -> None:
    """CompoundRiskAssessor 避難条件で source=compound_risk で blocked。"""
    fake_risk = MagicMock(
        should_evacuate=True,
        evacuation_reason="peg break",
        overall_risk=MagicMock(value="critical"),
        risk_score=Decimal("85"),
    )
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor") as cra_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.return_value = MagicMock(active=False, reason="")
        # assess は async（ThreadPoolExecutor + asyncio.run で await される）。
        cra_cls.return_value.assess = AsyncMock(return_value=fake_risk)
        r = evaluate_hard_stop(None, None, run_compound_risk=True)
    assert r.blocked
    assert r.source == "compound_risk"
    assert r.reason == "peg break"


def test_compound_failure_is_fail_open() -> None:
    """CompoundRiskAssessor 失敗は fail-open（継続 → blocked=False）。"""
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
        patch("app.protocols.risk.compound_risk.CompoundRiskAssessor") as cra_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.return_value = MagicMock(active=False, reason="")
        cra_cls.return_value.assess = MagicMock(side_effect=RuntimeError("assess boom"))
        r = evaluate_hard_stop(None, None, run_compound_risk=True)
    assert not r.blocked


def test_stress_safe_mode_blocks() -> None:
    """StressController が SAFE_MODE を返したら source=stress で blocked。"""
    from app.aave.schemas import AaveOperationMode

    mon = MagicMock()
    mon._last_price_change_24h = -15.0
    mon.is_trading_allowed.return_value = True

    stress_eval = MagicMock(mode=AaveOperationMode.SAFE_MODE, stage=2, reason="high volatility")
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch("app.automation.stress_controller.StressController") as stress_cls,
    ):
        stress_cls.return_value.evaluate.return_value = stress_eval
        r = evaluate_hard_stop(mon, Decimal("2.0"), run_compound_risk=False)
    assert r.blocked
    assert r.source == "stress"
    assert r.stress_stage == 2
    assert r.reason == "high volatility"


def test_stress_failure_skips_and_continues() -> None:
    """StressController 失敗は skip（継続）。後続 macro 通過で blocked=False。"""
    mon = MagicMock()
    mon._last_price_change_24h = -15.0
    mon.is_trading_allowed.return_value = True
    with (
        patch("app.automation.workflow.check_rule_engine", return_value=(True, "ok")),
        patch(
            "app.automation.stress_controller.StressController",
            side_effect=RuntimeError("stress boom"),
        ),
        patch("app.automation.macro_safe_mode.MacroSafeMode") as macro_cls,
    ):
        macro_cls.return_value.is_safe_mode_active.return_value = MagicMock(active=False, reason="")
        r = evaluate_hard_stop(mon, Decimal("2.0"), run_compound_risk=False)
    assert not r.blocked
