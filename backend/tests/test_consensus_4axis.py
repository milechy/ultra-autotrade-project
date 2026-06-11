# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for the 4-axis weighted consensus functions (docs/52 §7.1).

Covers:
- MultiAgentContext.weighted_directional_score()
- MultiAgentContext.weighted_confidence()
- MultiAgentContext.evaluate_4axis_consensus()
- resolve_llm_and_deterministic()
- validate_agent_weights()

Expected values are cross-checked against
docs/52_decision_layer_4axis_consensus_design.md Appendix A.1-A.3.
"""

import logging
from decimal import Decimal
from typing import Optional

import pytest

from app.ai.agents import (
    AgentSignal,
    Bias,
    MultiAgentContext,
    resolve_llm_and_deterministic,
    validate_agent_weights,
)
from app.ai.schemas import DeterministicVerdict, TradeAction


def _signal(name: str, bias: Bias, confidence: int) -> AgentSignal:
    return AgentSignal(
        agent_name=name,
        bias=bias,
        confidence=confidence,
        reasoning="test signal",
    )


def _make_ctx(
    indicator: Optional[tuple[Bias, int]] = None,
    pattern: Optional[tuple[Bias, int]] = None,
    risk: Optional[tuple[Bias, int]] = None,
    macro: Optional[tuple[Bias, int]] = None,
) -> MultiAgentContext:
    """Build a MultiAgentContext from (bias, confidence) tuples per axis."""
    return MultiAgentContext(
        indicator_signal=_signal("Indicator Agent", *indicator) if indicator else None,
        pattern_signal=_signal("Pattern Agent", *pattern) if pattern else None,
        risk_signal=_signal("Risk Agent", *risk) if risk else None,
        macro_signal=_signal("Macro Agent", *macro) if macro else None,
    )


class TestWeightedDirectionalScore:
    def test_weighted_score_all_bullish_max(self) -> None:
        """4 axes BULLISH conf=100 → score = +1.0, conf = 100."""
        ctx = _make_ctx(
            indicator=(Bias.BULLISH, 100),
            pattern=(Bias.BULLISH, 100),
            risk=(Bias.BULLISH, 100),
            macro=(Bias.BULLISH, 100),
        )
        assert ctx.weighted_directional_score() == Decimal("1.0")
        assert ctx.weighted_confidence() == 100

    def test_weighted_score_all_bearish_max(self) -> None:
        """4 axes BEARISH conf=100 → score = -1.0, conf = 100."""
        ctx = _make_ctx(
            indicator=(Bias.BEARISH, 100),
            pattern=(Bias.BEARISH, 100),
            risk=(Bias.BEARISH, 100),
            macro=(Bias.BEARISH, 100),
        )
        assert ctx.weighted_directional_score() == Decimal("-1.0")
        assert ctx.weighted_confidence() == 100

    def test_weighted_score_cancellation(self) -> None:
        """Indicator BULLISH 90 vs Macro BEARISH 90 mostly cancel out.

        score = 0.25×0.90 − 0.20×0.90 = 0.225 − 0.180 = +0.045 → HOLD.
        """
        ctx = _make_ctx(
            indicator=(Bias.BULLISH, 90),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.NEUTRAL, 50),
            macro=(Bias.BEARISH, 90),
        )
        assert ctx.weighted_directional_score() == Decimal("0.045")
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.HOLD

    def test_weighted_score_risk_dominant(self) -> None:
        """Risk BEARISH 80 alone: score = -0.32, agreeing_count = 1 → HOLD.

        R2(c): Risk 単独 BEARISH 80 は |score|=0.32 < threshold 0.40 で HOLD
        (閾値分岐での HOLD 到達。§4.4 降格ガード自体の検証は
        test_single_agent_runaway_demotion を参照)。
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BEARISH, 80),
            macro=(Bias.NEUTRAL, 45),
        )
        assert ctx.weighted_directional_score() == Decimal("-0.32")
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.agreeing_count == 1
        assert verdict.action == TradeAction.HOLD


class TestWeightedConfidence:
    def test_weighted_conf_arithmetic(self) -> None:
        """Appendix A.1: 0.25×75 + 0.15×40 + 0.40×80 + 0.20×65 = 69.75 → 70.

        ROUND_HALF_UP must produce 70 (built-in round() banker's rounding is
        forbidden by design).
        """
        ctx = _make_ctx(
            indicator=(Bias.BULLISH, 75),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BULLISH, 80),
            macro=(Bias.BULLISH, 65),
        )
        assert ctx.weighted_confidence() == 70


class TestEvaluate4AxisConsensus:
    def test_evaluate_consensus_buy(self) -> None:
        """Appendix A.1: score=+0.6375, conf=70, agreeing=3 → BUY."""
        ctx = _make_ctx(
            indicator=(Bias.BULLISH, 75),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BULLISH, 80),
            macro=(Bias.BULLISH, 65),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.BUY
        assert verdict.score == Decimal("0.6375")
        assert verdict.weighted_confidence == 70
        assert verdict.agreeing_count == 3
        assert set(verdict.per_agent_contribution.keys()) == {
            "risk",
            "indicator",
            "macro",
            "pattern",
        }
        assert verdict.per_agent_contribution["risk"].contribution == Decimal("0.32")
        assert verdict.per_agent_contribution["pattern"].contribution == Decimal("0")

    def test_evaluate_consensus_sell(self) -> None:
        """Indicator+Risk BEARISH 80 + Macro BEARISH 70 → SELL.

        score = −0.20 − 0.32 − 0.14 = −0.66, conf = 20+6+32+14 = 72.
        """
        ctx = _make_ctx(
            indicator=(Bias.BEARISH, 80),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BEARISH, 80),
            macro=(Bias.BEARISH, 70),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.SELL
        assert verdict.score == Decimal("-0.66")
        assert verdict.weighted_confidence == 72
        assert verdict.agreeing_count == 3

    def test_evaluate_consensus_macro_stuck_no_sell(self) -> None:
        """Appendix A.2: Macro BEARISH 95 alone must NOT produce SELL.

        SELL-spam (#365) recurrence prevention key test:
        score = −0.190, |score| < 0.40 → HOLD.
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 35),
            risk=(Bias.NEUTRAL, 45),
            macro=(Bias.BEARISH, 95),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.HOLD
        assert verdict.score == Decimal("-0.190")

    def test_single_agent_runaway_demotion(self) -> None:
        """§4.4 降格ガード: 閾値を超えても agreeing_count < 2 なら HOLD に降格。

        risk=BULLISH 100 + 他 3 軸 NEUTRAL 90:
        score = 0.40×1.00 = 0.40 (>= +0.40)、conf = 40+22.5+18+13.5 = 94 (>= 65)
        → 閾値分岐は BUY だが agreeing_count = 1 → HOLD 降格 (#365 再発防止の核心)。
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 90),
            pattern=(Bias.NEUTRAL, 90),
            risk=(Bias.BULLISH, 100),
            macro=(Bias.NEUTRAL, 90),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.score == Decimal("0.40")
        assert verdict.weighted_confidence == 94
        assert verdict.agreeing_count == 1
        assert verdict.action == TradeAction.HOLD
        assert "Demoted" in verdict.reasoning

    def test_missing_signal_counts_as_zero(self) -> None:
        """A missing axis contributes (direction=0, conf=0) without re-normalizing."""
        ctx = _make_ctx(risk=(Bias.BULLISH, 100))
        assert ctx.weighted_directional_score() == Decimal("0.40")
        assert ctx.weighted_confidence() == 40
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.HOLD
        assert verdict.per_agent_contribution["indicator"].direction == 0
        assert verdict.per_agent_contribution["indicator"].confidence == 0


class TestResolveLlmAndDeterministic:
    def _det_hold(self) -> DeterministicVerdict:
        """Deterministic HOLD verdict (Appendix A.2 macro-stuck context)."""
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 35),
            risk=(Bias.NEUTRAL, 45),
            macro=(Bias.BEARISH, 95),
        )
        return ctx.evaluate_4axis_consensus()

    def _det_sell(self) -> DeterministicVerdict:
        ctx = _make_ctx(
            indicator=(Bias.BEARISH, 80),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BEARISH, 80),
            macro=(Bias.BEARISH, 70),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.SELL  # sanity
        return verdict

    def test_post_llm_veto_llm_buy_det_hold(self) -> None:
        """LLM=BUY, det=HOLD → HOLD, veto_applied=True, confidence <= 50."""
        det = self._det_hold()
        action, confidence, veto_applied = resolve_llm_and_deterministic(TradeAction.BUY, 80, det)
        assert action == TradeAction.HOLD
        assert veto_applied is True
        assert confidence <= 50

    def test_post_llm_conflict_buy_vs_sell(self, caplog: pytest.LogCaptureFixture) -> None:
        """LLM=BUY vs det=SELL → HOLD + warning log (docs/52 §4.5)."""
        det = self._det_sell()
        with caplog.at_level(logging.WARNING, logger="app.ai.agents"):
            action, confidence, veto_applied = resolve_llm_and_deterministic(
                TradeAction.BUY, 80, det
            )
        assert action == TradeAction.HOLD
        assert veto_applied is True
        assert confidence <= 50
        assert any("conflict" in record.message.lower() for record in caplog.records)

    def test_llm_hold_always_holds_without_veto(self) -> None:
        """LLM=HOLD → HOLD regardless of det (existing behaviour, no veto)."""
        det = self._det_sell()
        action, confidence, veto_applied = resolve_llm_and_deterministic(TradeAction.HOLD, 90, det)
        assert action == TradeAction.HOLD
        assert veto_applied is False
        assert confidence == min(90, det.weighted_confidence)

    def test_llm_matches_det_adopts_action(self) -> None:
        """LLM=SELL, det=SELL → SELL, confidence = min(llm, det), no veto."""
        det = self._det_sell()
        action, confidence, veto_applied = resolve_llm_and_deterministic(TradeAction.SELL, 90, det)
        assert action == TradeAction.SELL
        assert veto_applied is False
        assert confidence == min(90, det.weighted_confidence)


class TestWeightValidation:
    def test_weight_env_override(self) -> None:
        """Custom weights argument is reflected in the calculation."""
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 40),
            risk=(Bias.BEARISH, 80),
            macro=(Bias.NEUTRAL, 45),
        )
        custom = {
            "risk": Decimal("0.25"),
            "indicator": Decimal("0.25"),
            "macro": Decimal("0.25"),
            "pattern": Decimal("0.25"),
        }
        # Default weights: risk=0.40 → score = -0.32
        assert ctx.weighted_directional_score() == Decimal("-0.32")
        # Custom weights: risk=0.25 → score = -0.20
        assert ctx.weighted_directional_score(custom) == Decimal("-0.20")
        verdict = ctx.evaluate_4axis_consensus(weights=custom)
        assert verdict.per_agent_contribution["risk"].weight == Decimal("0.25")

    def test_weight_validation_fails(self) -> None:
        """Weights summing to 1.5 must raise ValueError (fail-closed)."""
        bad_weights = {
            "risk": Decimal("0.50"),
            "indicator": Decimal("0.40"),
            "macro": Decimal("0.30"),
            "pattern": Decimal("0.30"),
        }
        with pytest.raises(ValueError, match="sum"):
            validate_agent_weights(bad_weights)
        ctx = _make_ctx(risk=(Bias.BULLISH, 80))
        with pytest.raises(ValueError, match="sum"):
            ctx.weighted_directional_score(bad_weights)
        with pytest.raises(ValueError, match="sum"):
            ctx.evaluate_4axis_consensus(weights=bad_weights)

    def test_weight_validation_rejects_negative_weight(self) -> None:
        """負の重みは合計が 1.0 でも拒否 (direction 反転 / score 不変条件破壊防止)。"""
        negative_weights = {
            "risk": Decimal("1.5"),
            "indicator": Decimal("-0.5"),
            "macro": Decimal("0"),
            "pattern": Decimal("0"),
        }
        with pytest.raises(ValueError, match="range"):
            validate_agent_weights(negative_weights)
        ctx = _make_ctx(risk=(Bias.BULLISH, 80))
        with pytest.raises(ValueError, match="range"):
            ctx.weighted_directional_score(negative_weights)

    def test_weight_validation_rejects_wrong_keys(self) -> None:
        """Key set must be exactly {risk, indicator, macro, pattern}."""
        with pytest.raises(ValueError, match="keys"):
            validate_agent_weights(
                {
                    "risk": Decimal("0.50"),
                    "indicator": Decimal("0.50"),
                }
            )
