# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Tests for the SELL/BUY AND-condition fix (fix/ai-sell-and-condition-20260521).

Root cause: v4 prompt allowed a single BEARISH agent (Indicator OR Macro) with
confidence ≥70% to trigger SELL, causing Macro Agent's continuous BEARISH to
fire repeated SELL signals.

Fix: Both Indicator AND Macro must independently agree on the same direction
≥70% (AND-condition). Enforced at the Python rule engine level (service.py
Guard 2) and documented in the v4/v5 prompts.

These tests are deterministic — no LLM calls are made.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.ai.agents import (
    AgentSignal,
    Bias,
    MultiAgentContext,
)
from app.ai.prompts import PROMPT_REGISTRY, get_prompt_template
from app.ai.schemas import (
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    RAGContext,
    TradeAction,
)
from app.ai.service import AIService
from app.data_feeds.context import build_market_context
from app.data_feeds.finance_feed import FinanceFeedResult
from app.data_feeds.geopolitical import GeoRiskResult
from app.data_feeds.news_feed import NewsFeedResult

# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_agent_signal(
    name: str,
    bias: Bias,
    confidence: int,
    reasoning: str = "",
) -> AgentSignal:
    return AgentSignal(
        agent_name=name,
        bias=bias,
        confidence=confidence,
        reasoning=reasoning or f"{bias.value} signal",
    )


def _make_cross_result(
    action: TradeAction, confidence: int = 75, version: str = "v5"
) -> CrossValidationResult:
    decision = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=confidence,
        reason=f"LLM proposed {action.value}",
        prompt_version=version,
    )
    return CrossValidationResult(
        primary=decision,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=confidence,
        final_reason=decision.reason,
        prompt_version=version,
    )


def _make_rag_context() -> RAGContext:
    return RAGContext(chunks=["(no context)"], query="market update", source_count=0)


# ---------------------------------------------------------------------------
# Tests: MultiAgentContext AND-condition methods
# ---------------------------------------------------------------------------


class TestIndicatorAndMacroAgreeBearish:
    """Unit tests for MultiAgentContext.indicator_and_macro_agree_bearish()."""

    def test_both_bearish_high_confidence_returns_true(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 80),
        )
        assert mac.indicator_and_macro_agree_bearish() is True

    def test_only_macro_bearish_returns_false(self) -> None:
        """Root cause scenario: only Macro is BEARISH — must NOT trigger SELL."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.NEUTRAL, 50),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 80),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_only_indicator_bearish_returns_false(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.NEUTRAL, 50),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_both_bearish_but_low_confidence_returns_false(self) -> None:
        """Confidence must be ≥70 for both."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 65),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 65),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_macro_low_confidence_blocks_condition(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 60),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_indicator_missing_returns_false(self) -> None:
        mac = MultiAgentContext(
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 80),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_macro_missing_returns_false(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_both_bearish_at_threshold_returns_true(self) -> None:
        """Exactly 70 confidence should satisfy the condition."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 70),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 70),
        )
        assert mac.indicator_and_macro_agree_bearish() is True

    def test_both_bullish_does_not_satisfy_bearish(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.BULLISH, 75),
        )
        assert mac.indicator_and_macro_agree_bearish() is False


class TestIndicatorAndMacroAgreeBullish:
    """Unit tests for MultiAgentContext.indicator_and_macro_agree_bullish()."""

    def test_both_bullish_high_confidence_returns_true(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.BULLISH, 80),
        )
        assert mac.indicator_and_macro_agree_bullish() is True

    def test_only_macro_bullish_returns_false(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.NEUTRAL, 50),
            macro_signal=_make_agent_signal("Macro", Bias.BULLISH, 80),
        )
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_only_indicator_bullish_returns_false(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.NEUTRAL, 50),
        )
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_both_bullish_but_low_confidence_returns_false(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 65),
            macro_signal=_make_agent_signal("Macro", Bias.BULLISH, 65),
        )
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_both_bearish_does_not_satisfy_bullish(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 75),
            macro_signal=_make_agent_signal("Macro", Bias.BEARISH, 75),
        )
        assert mac.indicator_and_macro_agree_bullish() is False


# ---------------------------------------------------------------------------
# Tests: service.py AND-condition guard (post-LLM clamping)
# ---------------------------------------------------------------------------


class TestJudgeWithRagAndConditionGuard:
    """Integration tests for the AND-condition guard in judge_with_rag.

    These tests mock the LLM calls and verify that the rule engine
    correctly clamps SELL/BUY to HOLD when the AND-condition is not met.
    """

    def _make_service(self) -> AIService:
        return AIService()

    def _make_settings(self, version: str = "v5") -> MagicMock:
        settings = MagicMock()
        settings.prompt_version = version
        settings.anthropic_api_key = "fake-key"
        settings.openai_api_key = None
        settings.cross_validation_enabled = False
        settings.shadow_mode = False
        settings.claude_model = "claude-opus-4-5"
        return settings

    def test_sell_blocked_when_only_macro_bearish(self) -> None:
        """
        Root cause scenario: LLM proposes SELL because Macro is BEARISH ≥70%.
        AND-condition guard must clamp result to HOLD when Indicator is not BEARISH.
        """
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        # Macro BEARISH 80%, Indicator NEUTRAL — AND-condition NOT met
        fin = FinanceFeedResult(fed_stance="hawkish")
        news = NewsFeedResult(sentiment="negative", summary="Rate hike fears")
        ctx = build_market_context(
            health_factor=Decimal("2.2"),  # Indicator will be BULLISH (high HF)
            finance=fin,
            news=news,
        )

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.SELL, 75).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        assert result.final_action == TradeAction.HOLD, (
            "SELL must be blocked when only Macro is BEARISH (AND-condition not met)"
        )
        assert "AND-condition" in result.final_reason

    def test_sell_allowed_when_both_indicator_and_macro_bearish(self) -> None:
        """
        SELL is permitted when BOTH Indicator (low HF) AND Macro (hawkish + negative)
        are BEARISH ≥70%.
        """
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        # Indicator BEARISH: low HF (1.45) + high utilization → score well below 35
        # Macro BEARISH: hawkish FED + negative news
        fin = FinanceFeedResult(
            fed_stance="hawkish",
            macro_summary="FED raises rates aggressively",
        )
        news = NewsFeedResult(
            sentiment="negative",
            summary="Market crash fears amid rate hikes",
        )
        ctx = build_market_context(
            health_factor=Decimal("1.45"),  # critically low → BEARISH, high confidence
            aave_utilization_rate=Decimal("92"),
            finance=fin,
            news=news,
        )

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.SELL, 78).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        # Both agents are BEARISH — AND-condition met — SELL should pass through
        assert result.final_action == TradeAction.SELL, (
            "SELL must be allowed when both Indicator AND Macro are BEARISH ≥70%"
        )

    def test_buy_blocked_when_only_macro_bullish(self) -> None:
        """BUY blocked when only Macro is BULLISH (Indicator is NEUTRAL/BEARISH)."""
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        fin = FinanceFeedResult(fed_stance="dovish")
        news = NewsFeedResult(sentiment="positive", summary="FED cuts rates")
        # Indicator BEARISH: low HF
        ctx = build_market_context(
            health_factor=Decimal("1.45"),
            finance=fin,
            news=news,
        )

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.BUY, 72).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        assert result.final_action == TradeAction.HOLD, (
            "BUY must be blocked when only Macro is BULLISH (Indicator is BEARISH)"
        )

    def test_buy_allowed_when_both_indicator_and_macro_bullish(self) -> None:
        """BUY permitted when BOTH Indicator AND Macro are BULLISH ≥70%."""
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        fin = FinanceFeedResult(fed_stance="dovish", stablecoin_risk="low")
        news = NewsFeedResult(sentiment="positive", summary="ETH bull run confirmed")
        geo = GeoRiskResult(geo_risk_score=15, summary="Stable environment")
        # Indicator BULLISH: high HF, low utilization, good APY
        ctx = build_market_context(
            health_factor=Decimal("2.8"),
            aave_utilization_rate=Decimal("30"),
            aave_supply_apy=Decimal("7.0"),
            finance=fin,
            news=news,
            geo_risk=geo,
        )

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.BUY, 80).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        assert result.final_action == TradeAction.BUY, (
            "BUY must be allowed when both Indicator AND Macro are BULLISH ≥70%"
        )

    def test_hold_passes_through_regardless_of_and_condition(self) -> None:
        """HOLD from LLM is never blocked — AND-condition only affects SELL/BUY."""
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        ctx = build_market_context()  # minimal context

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.HOLD, 55).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        assert result.final_action == TradeAction.HOLD

    def test_and_condition_not_applied_for_v3(self) -> None:
        """AND-condition guard is v4/v5 only — v3 SELL should pass through unchanged."""
        svc = self._make_service()
        settings = self._make_settings(version="v3")

        # Macro BEARISH, Indicator NEUTRAL — same as root cause scenario
        fin = FinanceFeedResult(fed_stance="hawkish")
        news = NewsFeedResult(sentiment="negative", summary="Rate hike fears")
        ctx = build_market_context(
            health_factor=Decimal("2.2"),
            finance=fin,
            news=news,
        )

        with patch.object(
            svc,
            "_call_claude",
            return_value=_make_cross_result(TradeAction.SELL, 72, version="v3").primary,
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=ctx,
                settings=settings,
            )

        # v3 does not apply AND-condition guard — LLM result passes through
        assert result.final_action == TradeAction.SELL, (
            "v3 should not have AND-condition guard applied"
        )

    def test_no_market_context_skips_and_guard(self) -> None:
        """Without market_context, AND-condition guard is skipped."""
        svc = self._make_service()
        settings = self._make_settings(version="v5")

        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.SELL, 75).primary
        ):
            result = svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=None,  # No market context
                settings=settings,
            )

        # With no market context, no pre-LLM guard runs — LLM result passes through
        assert result.final_action == TradeAction.SELL


# ---------------------------------------------------------------------------
# Tests: JSON Schema / parse-fail→HOLD safety (CLAUDE.md security rule 10)
# ---------------------------------------------------------------------------


class TestParseFailureSafetyUnchanged:
    """Verify that the existing parse-fail→HOLD safety is not broken by the fix."""

    def test_parse_failure_still_returns_hold(self) -> None:
        svc = AIService()
        from app.ai.schemas import LLMProvider

        result = svc._parse_llm_response("invalid json {{", LLMProvider.CLAUDE)
        assert result.action == TradeAction.HOLD

    def test_invalid_action_string_still_returns_hold(self) -> None:
        import json

        svc = AIService()
        from app.ai.schemas import LLMProvider

        raw = json.dumps({"action": "MAYBE", "confidence": 70, "reason": "test"})
        result = svc._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.action == TradeAction.HOLD

    def test_low_confidence_llm_response_still_returns_hold(self) -> None:
        """_apply_safety_guards: confidence < 40 → HOLD (unchanged behavior)."""
        from datetime import datetime, timezone

        svc = AIService()
        from app.ai.schemas import AIAnalysisResult

        result = svc._apply_safety_guards(
            AIAnalysisResult(
                id="x",
                url="https://x.com",
                action=TradeAction.SELL,
                confidence=30,  # below 40 threshold
                sentiment="negative",
                reason="weak signal",
                timestamp=datetime.now(timezone.utc),
            )
        )
        assert result.action == TradeAction.HOLD


# ---------------------------------------------------------------------------
# Tests: Prompt registry — v4 AND-condition text, v5 existence
# ---------------------------------------------------------------------------


class TestPromptRegistry:
    def test_v5_prompt_exists(self) -> None:
        assert "v5" in PROMPT_REGISTRY

    def test_v5_prompt_contains_and_condition_language(self) -> None:
        v5 = get_prompt_template("v5")
        assert "AND" in v5.system_prompt
        assert (
            "Indicator Agent AND Macro Agent" in v5.system_prompt
            or "Indicator AND Macro" in v5.system_prompt
        )

    def test_v5_prompt_explicitly_blocks_single_agent_sell(self) -> None:
        v5 = get_prompt_template("v5")
        assert "single" in v5.system_prompt.lower() or "alone" in v5.system_prompt.lower()

    def test_v4_prompt_updated_to_and_condition(self) -> None:
        """v4 prompt SELL rule must now require AND, not OR for directional trades."""
        v4 = get_prompt_template("v4")
        # The SELL decision rule must require BOTH (AND), not single agent (OR)
        assert "SELL: BOTH" in v4.system_prompt or (
            "SELL" in v4.system_prompt and "AND" in v4.system_prompt
        )
        # Confirm "Indicator or Macro" does not appear as the SELL trigger rule
        # (it may still appear in comments or HOLD rule, so check the SELL line specifically)
        sell_lines = [
            line for line in v4.system_prompt.split("\n") if line.strip().startswith("- SELL:")
        ]
        assert sell_lines, "v4 must have a SELL rule line"
        assert "or Macro" not in sell_lines[0], f"v4 SELL rule must not use OR: {sell_lines[0]}"

    def test_v5_user_template_has_reminder(self) -> None:
        v5 = get_prompt_template("v5")
        assert "SELL requires" in v5.user_template or "BUY requires" in v5.user_template

    def test_all_prior_versions_still_exist(self) -> None:
        for version in ("v1", "v2", "v3", "v4"):
            assert version in PROMPT_REGISTRY, f"Version {version} must still exist"

    def test_list_versions_includes_v5(self) -> None:
        from app.ai.prompts import list_versions

        versions = list_versions()
        assert "v5" in versions
