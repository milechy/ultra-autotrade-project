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

import os
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
    key_data: dict[str, object] | None = None,
) -> AgentSignal:
    return AgentSignal(
        agent_name=name,
        bias=bias,
        confidence=confidence,
        reasoning=reasoning or f"{bias.value} signal",
        key_data=key_data or {},
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


class TestFedStanceUnknownBranch:
    """fed_stance="unknown" relaxes the AND-condition to Indicator-only (2026-05-26).

    Rationale: when FED data is unavailable (Perplexity Finance returned no
    parseable data → fed_stance="unknown"), the macro agent's confidence is
    pinned at the floor of 25 and AND-condition is permanently false. The fix
    drops the macro axis from the AND requirement specifically when
    fed_stance="unknown"; the COMPOUND RISK guard (service.py Guard 1) remains
    the safety net upstream.

    Symmetric on both BUY and SELL — see TestFedStanceNeutralBranch for the
    asymmetric T1-B treatment of fed_stance="neutral".
    """

    def test_unknown_with_indicator_bearish_only_returns_true(self) -> None:
        """fed_stance=unknown + Indicator BEARISH>=70 + Macro NEUTRAL → True."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 75),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "unknown"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is True

    def test_unknown_with_indicator_bullish_only_returns_true(self) -> None:
        """fed_stance=unknown + Indicator BULLISH>=70 + Macro NEUTRAL → True."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 75),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "unknown"},
            ),
        )
        assert mac.indicator_and_macro_agree_bullish() is True

    def test_unknown_ignores_opposite_macro_bias(self) -> None:
        """Under fed_stance=unknown, macro bias direction is disregarded entirely."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.BULLISH,
                75,
                key_data={"fed_stance": "unknown"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is True

    def test_unknown_still_requires_indicator_threshold(self) -> None:
        """Even under fed_stance=unknown, Indicator confidence must be >=70."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 65),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "unknown"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_unknown_still_requires_indicator_directional(self) -> None:
        """Under fed_stance=unknown, NEUTRAL indicator does not qualify."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.NEUTRAL, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "unknown"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is False
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_dovish_fed_stance_NOT_relaxed_when_indicator_disagrees(self) -> None:
        """Sanity: with a real macro signal (dovish), the AND requirement still holds."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.BULLISH,
                75,
                key_data={"fed_stance": "dovish"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_missing_fed_stance_key_falls_through_to_AND(self) -> None:
        """If key_data has no fed_stance entry at all, treat as the non-unknown path."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
            macro_signal=_make_agent_signal("Macro", Bias.NEUTRAL, 25),
        )
        assert mac.indicator_and_macro_agree_bearish() is False


class TestFedStanceNeutralBranch:
    """fed_stance="neutral" — ASYMMETRIC relaxation introduced by T1-B (2026-05-28).

    BUY side (indicator_and_macro_agree_bullish): macro axis is dropped, qualifies
    on Indicator BULLISH conf>=70 alone. Motivation: staging soak ran 100% HOLD
    because fed=neutral is the dominant non-directional macro state and macro
    confidence collapses to its 25 floor, making the AND requirement unreachable
    on the BUY path.

    SELL side (indicator_and_macro_agree_bearish): macro axis is NOT dropped.
    Rationale: #365 (SELL-spam) was caused by a single BEARISH agent firing
    repeated SELL. Indicator BEARISH conf>=70 is easy to reach on a single
    low-HF read, so relaxing SELL on neutral macro would reopen that failure.
    Real, directional macro (hawkish + sufficient confidence) is still required.
    """

    def test_neutral_bullish_indicator_only_returns_true(self) -> None:
        """T1-B: fed=neutral + Indicator BULLISH>=70 + Macro NEUTRAL → BUY qualifies."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 75),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bullish() is True

    def test_neutral_bearish_indicator_only_returns_false(self) -> None:
        """T1-B asymmetry / #365 guard: fed=neutral does NOT relax SELL."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is False

    def test_neutral_bullish_still_requires_indicator_threshold(self) -> None:
        """Even under fed=neutral relaxation, Indicator confidence must be >=70."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 65),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_neutral_bullish_still_requires_indicator_directional(self) -> None:
        """Under fed=neutral relaxation, NEUTRAL indicator does not qualify."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.NEUTRAL, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.NEUTRAL,
                25,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bullish() is False

    def test_neutral_ignores_opposite_macro_bias_bullish_side(self) -> None:
        """Under fed=neutral, macro bias direction is disregarded for BUY."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BULLISH, 80),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.BEARISH,
                40,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bullish() is True

    def test_neutral_does_not_promote_bearish_when_macro_already_bearish(self) -> None:
        """Asymmetry sanity: if Indicator is BEARISH but Macro is non-BEARISH on neutral,
        SELL is still blocked — exactly the #365 protection."""
        mac = MultiAgentContext(
            indicator_signal=_make_agent_signal("Indicator", Bias.BEARISH, 90),
            macro_signal=_make_agent_signal(
                "Macro",
                Bias.BULLISH,
                75,
                key_data={"fed_stance": "neutral"},
            ),
        )
        assert mac.indicator_and_macro_agree_bearish() is False


class TestMacroAgentFedNeutralLift:
    """T1-C (2026-05-28): macro_agent applies a +5 score lift on fed=neutral.

    Goal: nudge Macro out of the 25-confidence floor when news is positive, so
    Macro reaches directional territory under combined favourable signals. The
    lift is positive (bullish-direction), so it can only make a BEARISH outcome
    less likely — #365 (SELL-spam) is not reopened.
    """

    def test_neutral_with_quiet_news_yields_neutral_bias(self) -> None:
        from app.ai.agents import macro_agent
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            finance=FinanceFeedResult(fed_stance="neutral"),
            news=NewsFeedResult(sentiment="neutral", summary=""),
        )
        sig = macro_agent(ctx)
        assert sig.bias == Bias.NEUTRAL
        # 50 + 5 = 55 → confidence = max(25, abs(55-50)*2 + 25) = 35, up from the 25 floor.
        assert sig.confidence >= 30
        assert sig.key_data.get("fed_stance") == "neutral"

    def test_neutral_with_positive_news_promotes_bullish(self) -> None:
        """neutral fed (+5) + positive news (+15) → score 70 → BULLISH."""
        from app.ai.agents import macro_agent
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            finance=FinanceFeedResult(fed_stance="neutral"),
            news=NewsFeedResult(sentiment="positive", summary="DeFi adoption growing"),
        )
        sig = macro_agent(ctx)
        assert sig.bias == Bias.BULLISH

    def test_neutral_with_negative_news_stays_bearish_or_neutral(self) -> None:
        """neutral fed (+5) + negative news (-15) → score 40 → NEUTRAL (not BEARISH).
        Asymmetric lift cannot promote BEARISH on its own — confirms #365 safety."""
        from app.ai.agents import macro_agent
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            finance=FinanceFeedResult(fed_stance="neutral"),
            news=NewsFeedResult(sentiment="negative", summary="Liquidity drying up"),
        )
        sig = macro_agent(ctx)
        # score = 50 + 5 - 15 = 40 → NEUTRAL band (40 is not <=35, not >=65)
        assert sig.bias == Bias.NEUTRAL

    def test_hawkish_unaffected_by_neutral_lift(self) -> None:
        """hawkish still applies -15; neutral lift branch is mutually exclusive."""
        from app.ai.agents import macro_agent
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            finance=FinanceFeedResult(fed_stance="hawkish"),
            news=NewsFeedResult(sentiment="neutral", summary=""),
        )
        sig = macro_agent(ctx)
        assert sig.bias in (Bias.BEARISH, Bias.NEUTRAL)
        assert "neutral" not in (sig.key_data.get("fed_stance") or "")


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
        assert "テクニカル指標とマクロ環境" in result.final_reason

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


# ---------------------------------------------------------------------------
# Tests: staging-only demo macro-gate relax (HOLD→BUY on Indicator-only BULLISH)
# ---------------------------------------------------------------------------


class TestStagingDemoMacroRelax:
    """`AI_STAGING_RELAX_MACRO_GATE` のデモ用ゲート緩和。

    実 macro が directional でない (hawkish/neutral) → LLM は HOLD を返すが、
    フラグ有効 (かつ非 production) のときだけ Indicator 単独 BULLISH>=70% で
    HOLD→BUY に格上げする。**本番では絶対に発火しない**ことを保証する。
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

    def _indicator_bullish_hawkish_ctx(self):
        """Indicator BULLISH (高HF/低util/高APY) だが macro は hawkish=非directional。

        通常は LLM が HOLD → 緩和フラグ無しなら HOLD のまま。
        """
        fin = FinanceFeedResult(fed_stance="hawkish", stablecoin_risk="medium")
        news = NewsFeedResult(sentiment="positive", summary="AAVE rallies")
        return build_market_context(
            health_factor=Decimal("2.8"),
            aave_utilization_rate=Decimal("30"),
            aave_supply_apy=Decimal("7.0"),
            finance=fin,
            news=news,
        )

    def _judge_hold(self, svc: AIService, settings: MagicMock):
        with patch.object(
            svc, "_call_claude", return_value=_make_cross_result(TradeAction.HOLD, 51).primary
        ):
            return svc.judge_with_rag(
                query="market update",
                rag_context=_make_rag_context(),
                market_context=self._indicator_bullish_hawkish_ctx(),
                settings=settings,
            )

    def test_flag_off_keeps_hold(self) -> None:
        """既定 (フラグ未設定) では HOLD のまま (緩和は発火しない)。"""
        svc = self._make_service()
        settings = self._make_settings()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_STAGING_RELAX_MACRO_GATE", None)
            result = self._judge_hold(svc, settings)
        assert result.final_action == TradeAction.HOLD

    def test_flag_on_non_production_upgrades_to_buy(self) -> None:
        """フラグ有効 + 非 production + Indicator BULLISH>=70 → HOLD→BUY。"""
        svc = self._make_service()
        settings = self._make_settings()
        with patch.dict(
            os.environ,
            {"AI_STAGING_RELAX_MACRO_GATE": "true", "APP_ENV": "staging"},
        ):
            result = self._judge_hold(svc, settings)
        assert result.final_action == TradeAction.BUY

    def test_flag_on_production_is_ignored(self) -> None:
        """**本番安全**: APP_ENV=production ならフラグ有効でも HOLD のまま。"""
        svc = self._make_service()
        settings = self._make_settings()
        with patch.dict(
            os.environ,
            {"AI_STAGING_RELAX_MACRO_GATE": "true", "APP_ENV": "production"},
        ):
            result = self._judge_hold(svc, settings)
        assert result.final_action == TradeAction.HOLD

    def test_flag_on_but_indicator_not_bullish_keeps_hold(self) -> None:
        """Indicator が BULLISH>=70 でなければ緩和有効でも昇格しない。"""
        svc = self._make_service()
        settings = self._make_settings()
        # 低HF → Indicator は BULLISH にならない
        fin = FinanceFeedResult(fed_stance="hawkish")
        news = NewsFeedResult(sentiment="negative", summary="risk-off")
        ctx = build_market_context(health_factor=Decimal("1.45"), finance=fin, news=news)
        with patch.dict(
            os.environ,
            {"AI_STAGING_RELAX_MACRO_GATE": "true", "APP_ENV": "staging"},
        ):
            with patch.object(
                svc, "_call_claude", return_value=_make_cross_result(TradeAction.HOLD, 51).primary
            ):
                result = svc.judge_with_rag(
                    query="market update",
                    rag_context=_make_rag_context(),
                    market_context=ctx,
                    settings=settings,
                )
        assert result.final_action == TradeAction.HOLD
