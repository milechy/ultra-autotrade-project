# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Multi-Agent AI Judgment — QuantAgent-inspired architecture.

4 specialist agents analyze different aspects of the market,
then a Decision Agent synthesizes their signals into a final judgment.

Architecture (no LangGraph — pure Python async):
  IndicatorAgent → market metrics signal
  PatternAgent   → trend/behavioral signal
  RiskAgent      → composite risk signal
  MacroAgent     → macro-economic signal
       ↓
  DecisionAgent  → synthesize → BUY/SELL/HOLD

Each agent is a pure function: MarketContext → AgentSignal.
No side effects, no state, easily testable.
"""

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.judgment_log import CognitiveState
from app.data_feeds.context import MarketContext

logger = logging.getLogger(__name__)


# ============================================================
# Agent Signal Schemas
# ============================================================
class Bias(str, Enum):
    """Agent's directional bias."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class AgentSignal(BaseModel):
    """Output from a single specialist agent."""

    agent_name: str
    bias: Bias
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    key_data: dict[str, object] = Field(default_factory=dict)


class MultiAgentContext(BaseModel):
    """Combined output from all specialist agents.

    Fed into the Decision Agent (LLM) as structured context.
    """

    indicator_signal: Optional[AgentSignal] = None
    pattern_signal: Optional[AgentSignal] = None
    risk_signal: Optional[AgentSignal] = None
    macro_signal: Optional[AgentSignal] = None
    cognitive_state: Optional[CognitiveState] = None

    def to_decision_prompt(self) -> str:
        """Format all agent signals for the Decision Agent LLM prompt."""
        sections = []

        for signal in [
            self.indicator_signal,
            self.pattern_signal,
            self.risk_signal,
            self.macro_signal,
        ]:
            if signal:
                sections.append(
                    f"## {signal.agent_name}\n"
                    f"Bias: {signal.bias.value} | Confidence: {signal.confidence}%\n"
                    f"Reasoning: {signal.reasoning}\n"
                    f"Key data: {signal.key_data}"
                )

        if self.cognitive_state and self.cognitive_state.total_judgments > 0:
            sections.append(self.cognitive_state.to_prompt_context())

        return "\n\n".join(sections)

    def has_compound_risk(self) -> bool:
        """Return True if Risk Agent detected COMPOUND RISK.

        If True, the rule engine MUST force HOLD before LLM call.
        """
        if self.risk_signal and "COMPOUND RISK" in self.risk_signal.reasoning.upper():
            return True
        return False

    def consensus_bias(self) -> Bias:
        """Quick check: what's the majority bias among agents?"""
        biases = [
            s.bias
            for s in [
                self.indicator_signal,
                self.pattern_signal,
                self.risk_signal,
                self.macro_signal,
            ]
            if s is not None
        ]
        if not biases:
            return Bias.NEUTRAL

        bullish = sum(1 for b in biases if b == Bias.BULLISH)
        bearish = sum(1 for b in biases if b == Bias.BEARISH)

        if bullish > bearish and bullish > len(biases) / 2:
            return Bias.BULLISH
        if bearish > bullish and bearish > len(biases) / 2:
            return Bias.BEARISH
        return Bias.NEUTRAL

    def average_confidence(self) -> int:
        """Average confidence across all agents."""
        signals = [
            s
            for s in [
                self.indicator_signal,
                self.pattern_signal,
                self.risk_signal,
                self.macro_signal,
            ]
            if s is not None
        ]
        if not signals:
            return 50
        return int(sum(s.confidence for s in signals) / len(signals))

    # ------------------------------------------------------------------
    # SELL/BUY AND-condition guard (v4/v5 rule engine, 2026-05-21)
    # ------------------------------------------------------------------

    #: Minimum confidence required for either core agent to qualify as directional.
    _DIRECTIONAL_THRESHOLD: int = 70

    #: fed_stance values that drop the macro axis from the AND requirement.
    #: ASYMMETRIC BY DESIGN — see method docstrings below for the rationale.
    _BULLISH_RELAX_FED_STANCES: frozenset[str] = frozenset({"unknown", "neutral"})
    _BEARISH_RELAX_FED_STANCES: frozenset[str] = frozenset({"unknown"})

    def indicator_and_macro_agree_bearish(self) -> bool:
        """Return True only when BOTH Indicator AND Macro agents are BEARISH >= threshold.

        Purpose: prevent a single continuously-BEARISH Macro Agent from triggering
        repeated SELL signals (root cause of the SELL-spam issue, #365, on v4
        prompts).

        Evaluated by the Python rule engine BEFORE the LLM call so the guard is
        deterministic and cannot be overridden by the LLM's prompt interpretation.

        fed_stance="unknown" branch (2026-05-26): when the FED signal is
        unavailable (e.g. Perplexity Finance returned no usable data), the macro
        agent's confidence floor of 25 would permanently block SELL. In that case
        drop the macro axis from the AND requirement and qualify on Indicator
        alone. The COMPOUND RISK guard (service.py Guard 1, evaluated before this
        method) is the safety net that keeps SELL from running away in that mode.

        fed_stance="neutral" is INTENTIONALLY NOT relaxed on the SELL side
        (asymmetric vs. the BULLISH counterpart). Rationale: #365 root cause was a
        single BEARISH agent firing repeated SELL. Permitting Indicator-only SELL
        whenever the macro is merely "neutral" would reopen exactly that failure
        mode — neutral macro is the common case and Indicator BEARISH conf>=70 is
        easy to reach on a single low-HF read. Keeping the AND requirement on the
        SELL path means a real, directional macro vote (hawkish + sufficient
        confidence) is still required before any SELL can clear the guard.
        """
        ind = self.indicator_signal
        mac = self.macro_signal
        if ind is None or mac is None:
            return False
        if mac.key_data.get("fed_stance") in self._BEARISH_RELAX_FED_STANCES:
            return ind.bias == Bias.BEARISH and ind.confidence >= self._DIRECTIONAL_THRESHOLD
        return (
            ind.bias == Bias.BEARISH
            and ind.confidence >= self._DIRECTIONAL_THRESHOLD
            and mac.bias == Bias.BEARISH
            and mac.confidence >= self._DIRECTIONAL_THRESHOLD
        )

    def indicator_and_macro_agree_bullish(self) -> bool:
        """Return True only when BOTH Indicator AND Macro agents are BULLISH >= threshold.

        Symmetric AND guard to prevent single-agent BULLISH from triggering BUY,
        with an ASYMMETRIC neutral relaxation (see below) so BUY entries are not
        permanently blocked while the #365 SELL-spam guard is preserved.

        fed_stance="unknown" branch: same rationale as the BEARISH counterpart —
        when FED data is missing, the macro confidence floor of 25 makes AND
        unreachable.

        fed_stance="neutral" branch (T1-B, 2026-05-28): observed staging soak ran
        100% HOLD because the macro feed reports "neutral" (data present, no
        directional bias) far more often than "unknown", and the macro confidence
        collapses to its 25 floor. With Indicator BULLISH conf>=70 already
        achievable on favourable on-chain data (util<30, APY>5), the AND
        requirement is the lone hard block on the BUY path. Dropping the macro
        axis when fed=neutral lets favourable on-chain conditions clear the
        guard. The asymmetric choice (BUY relaxed, SELL not) is deliberate:
        permitting Indicator-only SELL on neutral macro reopens #365; Indicator-
        only BUY does not, because BUY proposals are clamped to $50-$2000 per
        user downstream and the COMPOUND RISK guard remains upstream of this
        method.
        """
        ind = self.indicator_signal
        mac = self.macro_signal
        if ind is None or mac is None:
            return False
        if mac.key_data.get("fed_stance") in self._BULLISH_RELAX_FED_STANCES:
            return ind.bias == Bias.BULLISH and ind.confidence >= self._DIRECTIONAL_THRESHOLD
        return (
            ind.bias == Bias.BULLISH
            and ind.confidence >= self._DIRECTIONAL_THRESHOLD
            and mac.bias == Bias.BULLISH
            and mac.confidence >= self._DIRECTIONAL_THRESHOLD
        )


# ============================================================
# Specialist Agents (pure functions — no side effects)
# ============================================================
def indicator_agent(ctx: MarketContext) -> AgentSignal:
    """Analyze Aave on-chain indicators (utilization, APY, HF).

    Scoring (2026-05-27 — neutral-stuck mitigation):
      The original three-tier HF curve produced a -25 step-function at HF=2.0
      (1.99 → -10, 2.00 → +15) and left the dominant "moderately healthy" case
      (HF 1.7-1.99 / util 50-80% / APY 2-4%) at score=40 → NEUTRAL, blocking the
      v4/v5 AND-condition (Indicator+Macro both ≥70% conf) and pinning soak HOLD
      at ~100%.

      Mitigation: replace the three-tier HF with a smoother five-band curve,
      reward moderate utilization (ample liquidity) instead of only <50%, and
      add a mild bearish nudge when supply APY collapses (yield compression).
      This lets realistic-but-favourable data clear score≥65 and confidence≥70.

    Rules (post-fix):
    - HF < 1.6 → strongly bearish; HF 1.6-1.75 → bearish; 1.75-1.9 → mild cau-
      tion; 1.9-2.1 → mild comfort; 2.1-2.5 → bullish; ≥2.5 → strongly bullish.
    - Util >85% → bearish; 70-85% → mild caution; 30-70% → mild comfort;
      <30% → bullish (ample liquidity).
    - Supply APY >5% → bullish (attractive yield); <1% → mild bearish (yield
      compression suggests over-supply / weak demand).
    """
    hf = ctx.health_factor
    util = ctx.aave_utilization_rate
    supply_apy = ctx.aave_supply_apy

    key_data: dict[str, object] = {}
    reasons: list[str] = []
    score = 50  # Start neutral

    if hf is not None:
        hf_float = float(hf)
        key_data["health_factor"] = str(hf)
        if hf_float < 1.6:
            score -= 40
            reasons.append(f"HF={hf} is critically low")
        elif hf_float < 1.75:
            score -= 18
            reasons.append(f"HF={hf} is thin — liquidation risk if price moves")
        elif hf_float < 1.9:
            score -= 6
            reasons.append(f"HF={hf} is acceptable but watch closely")
        elif hf_float < 2.1:
            score += 8
            reasons.append(f"HF={hf} provides reasonable buffer")
        elif hf_float < 2.5:
            score += 16
            reasons.append(f"HF={hf} provides comfortable buffer")
        else:
            score += 22
            reasons.append(f"HF={hf} provides ample buffer")

    if util is not None:
        util_float = float(util)
        key_data["utilization_rate"] = str(util)
        if util_float > 85:
            score -= 18
            reasons.append(f"Utilization at {util}% — heavy liquidity pressure")
        elif util_float > 70:
            score -= 4
            reasons.append(f"Utilization at {util}% — elevated, monitor")
        elif util_float >= 30:
            score += 6
            reasons.append(f"Utilization at {util}% — healthy liquidity")
        else:
            score += 12
            reasons.append(f"Utilization at {util}% — ample liquidity")

    if supply_apy is not None:
        apy_float = float(supply_apy)
        key_data["supply_apy"] = str(supply_apy)
        if apy_float > 5:
            score += 10
            reasons.append(f"Supply APY at {supply_apy}% — attractive yield")
        elif apy_float < 1:
            score -= 6
            reasons.append(f"Supply APY at {supply_apy}% — yield compressed, weak demand")

    if score >= 65:
        bias = Bias.BULLISH
    elif score <= 35:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL

    confidence = min(100, max(20, abs(score - 50) * 2 + 30))

    return AgentSignal(
        agent_name="Indicator Agent (Aave Metrics)",
        bias=bias,
        confidence=confidence,
        reasoning=". ".join(reasons) if reasons else "Insufficient on-chain data for analysis",
        key_data=key_data,
    )


def pattern_agent(ctx: MarketContext) -> AgentSignal:
    """Detect behavioral patterns from cognitive state.

    Rules:
    - Consecutive HOLDs > 3 → potential missed opportunity (slightly bullish)
    - Win rate < 40% → reduce confidence
    - Recent flip-flopping (BUY→SELL→HOLD) → neutral + low confidence
    """
    cs = ctx.cognitive_state
    key_data: dict[str, object] = {}
    reasons: list[str] = []
    score = 50

    if cs is None or cs.total_judgments == 0:
        return AgentSignal(
            agent_name="Pattern Agent (Behavioral Analysis)",
            bias=Bias.NEUTRAL,
            confidence=30,
            reasoning="No judgment history available for pattern detection",
            key_data={},
        )

    key_data["total_judgments"] = cs.total_judgments
    key_data["consecutive_holds"] = cs.consecutive_holds

    if cs.consecutive_holds >= 5:
        score += 15
        reasons.append(
            f"{cs.consecutive_holds} consecutive HOLDs — market normalized, "
            "consider if conditions now favor action"
        )
    elif cs.consecutive_holds >= 3:
        score += 5
        reasons.append(
            f"{cs.consecutive_holds} consecutive HOLDs — review if caution is still warranted"
        )

    if cs.win_rate is not None:
        key_data["win_rate"] = f"{cs.win_rate:.0%}"
        if cs.win_rate < 0.4:
            score -= 10
            reasons.append(f"Win rate {cs.win_rate:.0%} is below target — increase caution")
        elif cs.win_rate > 0.7:
            score += 10
            reasons.append(f"Win rate {cs.win_rate:.0%} is strong — model is performing well")

    # Detect flip-flopping
    if cs.recent_actions and len(cs.recent_actions) >= 3:
        recent = cs.recent_actions[-3:]
        if len(set(recent)) >= 3:
            score = 50  # Force neutral
            reasons.append(
                "Recent flip-flopping detected (BUY/SELL/HOLD) — recommend neutral stance"
            )

    if score >= 60:
        bias = Bias.BULLISH
    elif score <= 40:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL

    confidence = min(80, max(25, abs(score - 50) * 2 + 25))

    return AgentSignal(
        agent_name="Pattern Agent (Behavioral Analysis)",
        bias=bias,
        confidence=confidence,
        reasoning=". ".join(reasons) if reasons else "No significant patterns detected",
        key_data=key_data,
    )


def risk_agent(ctx: MarketContext) -> AgentSignal:
    """Evaluate composite risk from geopolitical, stablecoin, and HF data.

    Rules:
    - geo_risk > 70 → bearish (elevated global risk)
    - stablecoin_risk == "high" → bearish (depeg risk)
    - geo_risk < 30 AND stablecoin_risk == "low" → bullish
    - HF < 1.8 combined with high geo_risk → strongly bearish
    """
    geo = ctx.geo_risk
    key_data: dict[str, object] = {}
    reasons: list[str] = []
    score = 50

    key_data["geo_risk_score"] = geo.geo_risk_score
    key_data["geo_summary"] = geo.summary

    if geo.geo_risk_score >= 70:
        score -= 30
        reasons.append(f"Geopolitical risk {geo.geo_risk_score}/100 is elevated: {geo.summary}")
    elif geo.geo_risk_score >= 50:
        score -= 10
        reasons.append(f"Geopolitical risk {geo.geo_risk_score}/100 — moderate, monitor closely")
    elif geo.geo_risk_score < 30:
        score += 10
        reasons.append(f"Geopolitical risk {geo.geo_risk_score}/100 — low risk environment")

    stablecoin_risk = ctx.finance.stablecoin_risk
    key_data["stablecoin_risk"] = stablecoin_risk
    if stablecoin_risk == "high":
        score -= 25
        reasons.append("Stablecoin risk is HIGH — depeg concerns")
    elif stablecoin_risk == "medium":
        score -= 10
        reasons.append("Stablecoin risk is medium — watch reserves")

    # Combined risk: low HF + high geo = very dangerous
    if ctx.health_factor is not None and geo.geo_risk_score >= 60:
        if float(ctx.health_factor) < 1.8:
            score -= 20
            reasons.append(
                f"COMPOUND RISK: Low HF ({ctx.health_factor}) + elevated geo risk "
                f"({geo.geo_risk_score}) — high liquidation danger"
            )

    if score >= 60:
        bias = Bias.BULLISH
    elif score <= 35:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL

    confidence = min(90, max(30, abs(score - 50) * 2 + 30))

    return AgentSignal(
        agent_name="Risk Agent (Composite Risk Assessment)",
        bias=bias,
        confidence=confidence,
        reasoning=". ".join(reasons) if reasons else "Risk environment is stable",
        key_data=key_data,
    )


def macro_agent(ctx: MarketContext) -> AgentSignal:
    """Analyze macro-economic environment from news and finance feeds.

    Rules:
    - FED dovish → bullish for DeFi yields
    - FED hawkish → bearish (capital flows to TradFi)
    - Negative news sentiment → bearish
    - Positive news + dovish FED → strongly bullish
    """
    key_data: dict[str, object] = {}
    reasons: list[str] = []
    score = 50

    news = ctx.news
    sentiment = news.sentiment
    key_data["news_sentiment"] = sentiment
    if news.summary and "No news" not in news.summary:
        key_data["news_summary"] = news.summary[:100]
        if sentiment == "positive":
            score += 15
            reasons.append("News sentiment is positive for crypto/DeFi")
        elif sentiment == "negative":
            score -= 15
            reasons.append("News sentiment is negative — risk-off environment")

    fed = ctx.finance.fed_stance
    key_data["fed_stance"] = fed
    if fed == "dovish":
        score += 20
        reasons.append("FED dovish — favorable for yield-seeking in DeFi")
    elif fed == "hawkish":
        score -= 15
        reasons.append("FED hawkish — capital may flow to higher TradFi rates")
    elif fed == "neutral":
        # T1-C (2026-05-28): mild bullish lift on the BUY-side macro reading.
        # fed=neutral is the dominant staging case and used to leave score
        # untouched at 50 → confidence collapsed to the 25 floor. A small +5
        # nudge keeps bias=NEUTRAL but pushes confidence enough that, combined
        # with news=positive, Macro lands closer to directional. SELL path is
        # not affected: a +5 on neutral makes a BEARISH outcome strictly
        # harder, never easier — so #365 (SELL-spam) is not reopened by this.
        score += 5
        reasons.append("FED neutral — no immediate tightening, mildly supportive")

    if ctx.finance.key_indicators:
        key_data["indicators"] = ctx.finance.key_indicators[:3]

    if score >= 65:
        bias = Bias.BULLISH
    elif score <= 35:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL

    confidence = min(85, max(25, abs(score - 50) * 2 + 25))

    return AgentSignal(
        agent_name="Macro Agent (Economic Environment)",
        bias=bias,
        confidence=confidence,
        reasoning=". ".join(reasons) if reasons else "Macro data unavailable or neutral",
        key_data=key_data,
    )


# ============================================================
# Orchestrator: Run all agents → build MultiAgentContext
# ============================================================
def run_all_agents(ctx: MarketContext) -> MultiAgentContext:
    """Execute all specialist agents and combine their signals.

    Pure synchronous function — no LLM calls.
    Each agent is a rule-based analyzer that processes cached data.
    The actual LLM call happens in DecisionAgent (ai/service.py).
    """
    return MultiAgentContext(
        indicator_signal=indicator_agent(ctx),
        pattern_signal=pattern_agent(ctx),
        risk_signal=risk_agent(ctx),
        macro_signal=macro_agent(ctx),
        cognitive_state=ctx.cognitive_state,
    )
