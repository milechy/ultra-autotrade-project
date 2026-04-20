# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/service.py
"""
Service layer for AI analysis logic.

Responsibilities:
- Accept a NotionNewsItem and determine BUY / SELL / HOLD
- Apply judgment within the rules defined in docs/05_ai_judgement_rules.md
- Allow external LLM clients (OpenAI, etc.) to be swapped in
- Fail-safe to HOLD on errors or invalid values
"""

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional

from app.ai.agents import MultiAgentContext, run_all_agents
from app.ai.judgment_log import CognitiveState
from app.data_feeds.context import MarketContext
from app.notion.schemas import NotionNewsItem

from .config import DEFAULT_FALLBACK_MODEL, AISettings, get_ai_settings
from .prompts import get_prompt_template
from .schemas import (
    AIAnalysisResult,
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    RAGContext,
    TradeAction,
)

logger = logging.getLogger(__name__)


# LLM client type (expects a callable: NotionNewsItem -> AIAnalysisResult)
LLMAnalyzer = Callable[[NotionNewsItem], AIAnalysisResult]


class AIService:
    """
    Service class that accepts a list of news items and returns AI judgment results.

    - LLMAnalyzer can be injected via constructor (pass a mock in tests)
    - Defaults to a simple keyword-based rule judgment when no LLM is configured
    """

    def __init__(self, *, llm_analyzer: Optional[LLMAnalyzer] = None) -> None:
        self._llm_analyzer = llm_analyzer

    def analyze_items(self, items: Iterable[NotionNewsItem]) -> List[AIAnalysisResult]:
        """
        Accept an iterable of NotionNewsItem and return a list of AIAnalysisResult.
        """
        results: List[AIAnalysisResult] = []
        now = datetime.now(timezone.utc)

        for item in items:
            result = self._analyze_single(item, now)
            results.append(result)

        return results

    def _analyze_single(
        self,
        item: NotionNewsItem,
        now: Optional[datetime] = None,
    ) -> AIAnalysisResult:
        """
        Run judgment for a single news item.

        1. Use LLMAnalyzer if configured (takes priority)
        2. On exception or invalid values: log and fall back to HOLD
        3. If no LLMAnalyzer is available: use simple rule-based judgment
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Try LLMAnalyzer first if available
        if self._llm_analyzer is not None:
            try:
                llm_result = self._llm_analyzer(item)
                safe_result = self._apply_safety_guards(llm_result)
                return safe_result
            except Exception as exc:  # noqa: BLE001
                # Per security design: do not log news body text directly.
                # Record only minimal identifiers such as ID and URL.
                logger.warning(
                    "LLM analyzer failed; fallback to rule-based decision. id=%s url=%s error=%s",
                    getattr(item, "id", "unknown"),
                    getattr(item, "url", "unknown"),
                    exc,
                )

        # Fall back to simple rule-based judgment when LLM is not used or unavailable
        rule_based = self._rule_based_decision(item, now)
        safe_result = self._apply_safety_guards(rule_based)
        return safe_result

    def _apply_safety_guards(self, result: AIAnalysisResult) -> AIAnalysisResult:
        """
        Apply safety guards per the "safety valve" rules in docs/05_ai_judgement_rules.md.
        Converts to HOLD when confidence is too low or values are invalid.
        """
        # Clamp invalid confidence values
        confidence = result.confidence
        if confidence < 0:
            confidence = 0
        if confidence > 100:
            confidence = 100

        action = result.action

        # Force HOLD if confidence is below 40 or action is invalid
        if confidence < 40 or action not in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD):
            action = TradeAction.HOLD

        # Return a new instance with corrected values (original object is unchanged)
        return AIAnalysisResult(
            id=result.id,
            url=result.url,
            action=action,
            confidence=confidence,
            sentiment=result.sentiment,
            summary=result.summary,
            reason=result.reason,
            timestamp=result.timestamp,
        )

    def _rule_based_decision(
        self,
        item: NotionNewsItem,
        now: Optional[datetime] = None,
    ) -> AIAnalysisResult:
        """
        Simple keyword-based judgment that works without an LLM.

        - Intentionally rough logic, implemented as a Phase 2 starting point
        - Expected to be gradually replaced by LLMAnalyzer in production
        """
        if now is None:
            now = datetime.now(timezone.utc)

        text = " ".join(
            part
            for part in [
                getattr(item, "summary", None),
                getattr(item, "url", None),
            ]
            if part
        ).lower()

        # Very simple keyword lists
        positive_keywords = [
            "record profit",
            "record revenue",
            "profit grows",
            "bullish",
            "upgrade",
            "上方修正",
            "好調",
            "増益",
            "最高益",
            "成長",
        ]
        negative_keywords = [
            "fraud",
            "scandal",
            "bankruptcy",
            "lawsuit",
            "downgrade",
            "暴落",
            "下方修正",
            "不祥事",
            "破綻",
            "赤字",
        ]

        sentiment = "neutral"
        action = TradeAction.HOLD
        confidence = 50
        reason = "ニュース内容が中立または判断が難しいため、HOLD としました。"

        if any(keyword in text for keyword in positive_keywords):
            sentiment = "positive"
            action = TradeAction.BUY
            confidence = 80
            reason = "好材料が多く、市場にポジティブな影響が見込まれるため BUY 判定としました。"
        elif any(keyword in text for keyword in negative_keywords):
            sentiment = "negative"
            action = TradeAction.SELL
            confidence = 80
            reason = "悪材料が多く、市場にネガティブな影響が見込まれるため SELL 判定としました。"

        return AIAnalysisResult(
            id=getattr(item, "id", ""),
            url=getattr(item, "url", ""),
            action=action,
            confidence=confidence,
            sentiment=sentiment,
            summary=getattr(item, "summary", None),
            reason=reason,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Two-Phase AI Judge with RAG（Step 4 追加分）
    # ------------------------------------------------------------------

    def judge_with_rag(
        self,
        query: str,
        rag_context: RAGContext,
        *,
        market_context: Optional[MarketContext] = None,
        cognitive_state: Optional[CognitiveState] = None,
        settings: Optional[AISettings] = None,
    ) -> CrossValidationResult:
        """
        Two-phase AI judge with RAG context.
        Phase 1: Claude (primary)
        Phase 2: GPT-4o (secondary, cross-validation)
        プロンプトバージョンはsettings.prompt_versionで制御し、結果に含める。
        """
        ai_settings = settings or get_ai_settings()
        version = ai_settings.prompt_version

        # Rule engine: COMPOUND RISK → force HOLD before LLM call
        if market_context is not None:
            agent_ctx_check = run_all_agents(market_context)
            if agent_ctx_check.has_compound_risk():
                logger.warning("COMPOUND RISK detected by Risk Agent. Forcing HOLD.")
                compound_decision = LLMDecision(
                    provider=LLMProvider.RULE_BASED,
                    action=TradeAction.HOLD,
                    confidence=95,
                    reason="COMPOUND RISK: Low HF + elevated geo risk. Forced HOLD by rule engine.",
                    prompt_version=version,
                )
                return CrossValidationResult(
                    primary=compound_decision,
                    secondary=None,
                    agreed=True,
                    final_action=TradeAction.HOLD,
                    final_confidence=95,
                    final_reason="COMPOUND RISK detected. Rule engine forced HOLD before LLM call.",
                )

        system_prompt, user_content = self._build_rag_prompt(
            query, rag_context, version, market_context, cognitive_state
        )

        # Phase 1: Primary (Claude)
        primary = self._call_claude(system_prompt, user_content, ai_settings, version)

        # Phase 2: Secondary (OpenAI) - only if enabled and key available
        secondary = None
        if ai_settings.cross_validation_enabled and ai_settings.openai_api_key:
            secondary = self._call_openai(system_prompt, user_content, ai_settings, version)

        result = self._cross_validate(primary, secondary)

        # Shadow Mode: record judgment and attach shadow_mode flag before returning.
        # Caller should skip actual trade execution when shadow_mode=True.
        if ai_settings.shadow_mode:
            logger.info(
                "SHADOW_MODE | action=%s confidence=%s reason=%s prompt_version=%s",
                result.final_action.value,
                result.final_confidence,
                result.final_reason,
                result.prompt_version,
            )
            return result.model_copy(update={"shadow_mode": True})

        return result

    def _build_rag_prompt(
        self,
        query: str,
        rag_context: RAGContext,
        version: str = "v1",
        market_context: Optional[MarketContext] = None,
        cognitive_state: Optional[CognitiveState] = None,
    ) -> tuple[str, str]:
        """Build prompt with RAG context chunks using the specified prompt version.

        Returns (system_prompt, user_content) tuple so callers can use proper
        system/user role separation for each API (Anthropic system= param, OpenAI role=system).

        For v3: runs multi-agent analysis and injects agent_signals into the template itself.
        For v1/v2: appends agent analysis + market context as extra sections.
        """
        chunks_text = (
            "\n---\n".join(rag_context.chunks)
            if rag_context.chunks
            else "(No relevant context found)"
        )
        template = get_prompt_template(version)

        # Run multi-agent analysis if market context available (zero LLM cost)
        agent_ctx: Optional[MultiAgentContext] = None
        if market_context is not None:
            agent_ctx = run_all_agents(market_context)

        # Build user content — v3 injects agent_signals into the template itself
        if version == "v3":
            agent_signals_text = (
                agent_ctx.to_decision_prompt()
                if agent_ctx is not None
                else "(No agent signals available — market context not provided)"
            )
            user_content = template.user_template.format(
                agent_signals=agent_signals_text,
                context=chunks_text,
                query=query,
            )
        else:
            user_content = template.user_template.format(
                context=chunks_text,
                query=query,
            )
            # For v1/v2: append agent analysis and market context as extra sections
            if agent_ctx is not None:
                user_content = (
                    user_content + f"\n\n## Agent Analysis:\n{agent_ctx.to_decision_prompt()}"
                )
            if market_context is not None:
                ctx_text = market_context.to_prompt_context()
                user_content = user_content + f"\n\n## Market Context (Real-time Data):\n{ctx_text}"

        if cognitive_state is not None:
            user_content = user_content + f"\n\n{cognitive_state.to_prompt_context()}"

        return template.system_prompt, user_content

    def _call_claude(
        self,
        system_prompt: str,
        user_content: str,
        settings: AISettings,
        version: str = "v1",
    ) -> LLMDecision:
        """
        Call Claude API with Opus→Sonnet fallback.

        Retry logic:
        - Try Opus up to 2 times
        - If both attempts fail, switch to Sonnet (AI_FALLBACK_MODEL)
        - On fallback: decay confidence by 0.8x and set provider="claude_fallback"
        """
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set; falling back to HOLD")
            return LLMDecision(
                provider=LLMProvider.CLAUDE,
                action=TradeAction.HOLD,
                confidence=0,
                reason="API key not configured",
                prompt_version=version,
            )

        # Try Opus up to 2 times
        _MAX_OPUS_RETRIES = 2
        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_OPUS_RETRIES + 1):
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                response = client.messages.create(
                    model=settings.claude_model,
                    max_tokens=500,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                raw_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        raw_text = block.text
                        break
                decision = self._parse_llm_response(raw_text, LLMProvider.CLAUDE)
                return decision.model_copy(update={"prompt_version": version})
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Claude API call failed (attempt %d/%d): %s",
                    attempt,
                    _MAX_OPUS_RETRIES,
                    exc,
                )

        # Opus failed twice → fall back to Sonnet
        fallback_model = getattr(settings, "ai_fallback_model", DEFAULT_FALLBACK_MODEL)
        logger.warning(
            "Claude Opus failed after %d attempts; switching to fallback model=%s",
            _MAX_OPUS_RETRIES,
            fallback_model,
        )
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=fallback_model,
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            raw_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    raw_text = block.text
                    break
            decision = self._parse_llm_response(raw_text, LLMProvider.CLAUDE_FALLBACK)
            # Decay confidence by 0.8x on fallback (assuming lower accuracy from Sonnet)
            decayed_confidence = int(decision.confidence * 0.8)
            return decision.model_copy(
                update={
                    "confidence": decayed_confidence,
                    "provider": LLMProvider.CLAUDE_FALLBACK,
                    "prompt_version": version,
                }
            )
        except Exception as exc:
            logger.error("Claude fallback API call also failed: %s (original: %s)", exc, last_exc)
            return LLMDecision(
                provider=LLMProvider.CLAUDE_FALLBACK,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"Opus error: {last_exc}; Fallback error: {exc}",
                prompt_version=version,
            )

    def _call_openai(
        self,
        system_prompt: str,
        user_content: str,
        settings: AISettings,
        version: str = "v1",
    ) -> LLMDecision:
        """Call OpenAI API. Fail-closed: error→HOLD."""
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set; falling back to HOLD")
            return LLMDecision(
                provider=LLMProvider.OPENAI,
                action=TradeAction.HOLD,
                confidence=0,
                reason="API key not configured",
                prompt_version=version,
            )
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            decision = self._parse_llm_response(content, LLMProvider.OPENAI)
            return decision.model_copy(update={"prompt_version": version})
        except Exception as exc:
            logger.error("OpenAI API call failed: %s", exc)
            return LLMDecision(
                provider=LLMProvider.OPENAI,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"API error: {exc}",
                prompt_version=version,
            )

    def _parse_llm_response(self, raw: str, provider: LLMProvider) -> LLMDecision:
        """Parse JSON response from LLM. Parse failure→HOLD."""
        try:
            text = raw.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            action_str = data.get("action", "HOLD").upper()
            if action_str not in ("BUY", "SELL", "HOLD"):
                action_str = "HOLD"
            action = TradeAction(action_str)
            confidence = max(0, min(100, int(data.get("confidence", 0))))
            reason = data.get("reason", "")
            return LLMDecision(
                provider=provider,
                action=action,
                confidence=confidence,
                reason=reason,
                raw_response=raw,
            )
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse LLM response from %s: %s", provider.value, exc)
            return LLMDecision(
                provider=provider,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"Parse error: {exc}",
                raw_response=raw,
            )

    def _cross_validate(
        self, primary: LLMDecision, secondary: Optional[LLMDecision]
    ) -> CrossValidationResult:
        """
        Cross-validation logic:
        - No secondary → use primary
        - Both agree → average confidence
        - Disagree → HOLD (fail-closed)
        """
        if secondary is None:
            return CrossValidationResult(
                primary=primary,
                secondary=None,
                agreed=True,
                final_action=primary.action,
                final_confidence=primary.confidence,
                final_reason=primary.reason,
                prompt_version=primary.prompt_version,
            )

        agreed = primary.action == secondary.action
        if agreed:
            avg_confidence = (primary.confidence + secondary.confidence) // 2
            return CrossValidationResult(
                primary=primary,
                secondary=secondary,
                agreed=True,
                final_action=primary.action,
                final_confidence=avg_confidence,
                final_reason=f"Both LLMs agree: {primary.reason}",
                prompt_version=primary.prompt_version,
            )
        else:
            min_confidence = min(primary.confidence, secondary.confidence)
            return CrossValidationResult(
                primary=primary,
                secondary=secondary,
                agreed=False,
                final_action=TradeAction.HOLD,
                final_confidence=min(min_confidence, 30),
                final_reason=(
                    f"LLMs disagree ({primary.action.value} vs {secondary.action.value});"
                    " defaulting to HOLD"
                ),
                prompt_version=primary.prompt_version,
            )
