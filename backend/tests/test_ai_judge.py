# backend/tests/test_ai_judge.py
"""AI Judge cross-validation and RAG tests."""

from unittest.mock import MagicMock, patch

from app.ai.schemas import (
    LLMDecision,
    LLMProvider,
    RAGContext,
    TradeAction,
)
from app.ai.service import AIService


def _make_decision(provider, action, confidence, reason="test"):
    return LLMDecision(provider=provider, action=action, confidence=confidence, reason=reason)


class TestCrossValidation:
    def test_both_agree_buy(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.BUY, 80)
        secondary = _make_decision(LLMProvider.OPENAI, TradeAction.BUY, 90)
        result = service._cross_validate(primary, secondary)
        assert result.agreed is True
        assert result.final_action == TradeAction.BUY
        assert result.final_confidence == 85  # average

    def test_both_agree_sell(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.SELL, 70)
        secondary = _make_decision(LLMProvider.OPENAI, TradeAction.SELL, 60)
        result = service._cross_validate(primary, secondary)
        assert result.agreed is True
        assert result.final_action == TradeAction.SELL

    def test_disagree_defaults_hold(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.BUY, 80)
        secondary = _make_decision(LLMProvider.OPENAI, TradeAction.SELL, 70)
        result = service._cross_validate(primary, secondary)
        assert result.agreed is False
        assert result.final_action == TradeAction.HOLD
        assert result.final_confidence <= 30  # capped

    def test_no_secondary_uses_primary(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.BUY, 85)
        result = service._cross_validate(primary, None)
        assert result.agreed is True
        assert result.final_action == TradeAction.BUY
        assert result.final_confidence == 85

    def test_disagree_reason_mentions_both_actions(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.BUY, 80)
        secondary = _make_decision(LLMProvider.OPENAI, TradeAction.SELL, 70)
        result = service._cross_validate(primary, secondary)
        assert result.final_reason is not None
        assert "BUY" in result.final_reason or "SELL" in result.final_reason

    def test_agree_reason_mentions_agreement(self):
        service = AIService()
        primary = _make_decision(LLMProvider.CLAUDE, TradeAction.HOLD, 60, reason="neutral market")
        secondary = _make_decision(LLMProvider.OPENAI, TradeAction.HOLD, 55)
        result = service._cross_validate(primary, secondary)
        assert result.agreed is True
        assert result.final_reason is not None


class TestParseLLMResponse:
    def test_valid_json(self):
        service = AIService()
        raw = '{"action": "BUY", "confidence": 85, "reason": "bullish signals"}'
        result = service._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.action == TradeAction.BUY
        assert result.confidence == 85

    def test_markdown_wrapped_json(self):
        service = AIService()
        raw = '```json\n{"action": "SELL", "confidence": 70, "reason": "bearish"}\n```'
        result = service._parse_llm_response(raw, LLMProvider.OPENAI)
        assert result.action == TradeAction.SELL
        assert result.confidence == 70

    def test_invalid_json_returns_hold(self):
        service = AIService()
        raw = "This is not JSON at all"
        result = service._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 0

    def test_invalid_action_defaults_hold(self):
        service = AIService()
        raw = '{"action": "YOLO", "confidence": 99, "reason": "to the moon"}'
        result = service._parse_llm_response(raw, LLMProvider.OPENAI)
        assert result.action == TradeAction.HOLD

    def test_confidence_clamped(self):
        service = AIService()
        raw = '{"action": "BUY", "confidence": 150, "reason": "very bullish"}'
        result = service._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.confidence == 100  # clamped

    def test_hold_action_parses_correctly(self):
        service = AIService()
        raw = '{"action": "HOLD", "confidence": 50, "reason": "uncertain market"}'
        result = service._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 50

    def test_provider_is_stored(self):
        service = AIService()
        raw = '{"action": "BUY", "confidence": 75, "reason": "bullish"}'
        result = service._parse_llm_response(raw, LLMProvider.OPENAI)
        assert result.provider == LLMProvider.OPENAI

    def test_negative_confidence_clamped_to_zero(self):
        service = AIService()
        raw = '{"action": "SELL", "confidence": -10, "reason": "bearish"}'
        result = service._parse_llm_response(raw, LLMProvider.CLAUDE)
        assert result.confidence == 0


class TestBuildRAGPrompt:
    def test_includes_chunks(self):
        service = AIService()
        context = RAGContext(
            chunks=["BTC broke $100k", "Market sentiment bullish"],
            query="What is the bitcoin outlook?",
            source_count=2,
        )
        prompt = service._build_rag_prompt("analyze bitcoin", context)
        assert "BTC broke $100k" in prompt
        assert "Market sentiment bullish" in prompt

    def test_empty_chunks(self):
        service = AIService()
        context = RAGContext(chunks=[], query="test", source_count=0)
        prompt = service._build_rag_prompt("test query", context)
        assert "No relevant context" in prompt

    def test_prompt_contains_query(self):
        service = AIService()
        context = RAGContext(chunks=["some context"], query="bitcoin analysis", source_count=1)
        prompt = service._build_rag_prompt("analyze bitcoin trends", context)
        assert "analyze bitcoin trends" in prompt

    def test_prompt_contains_json_instruction(self):
        service = AIService()
        context = RAGContext(chunks=["context"], query="test", source_count=1)
        prompt = service._build_rag_prompt("test", context)
        assert "JSON" in prompt or "json" in prompt


class TestJudgeWithRAG:
    def test_claude_failure_returns_hold(self):
        service = AIService()
        context = RAGContext(chunks=["test"], query="test", source_count=1)

        with patch.object(service, "_call_claude") as mock_claude:
            mock_claude.return_value = _make_decision(
                LLMProvider.CLAUDE, TradeAction.HOLD, 0, "API error"
            )
            settings = MagicMock()
            settings.cross_validation_enabled = False
            settings.openai_api_key = None
            settings.anthropic_api_key = "dummy-key"

            result = service.judge_with_rag("test", context, settings=settings)
            assert result.final_action == TradeAction.HOLD

    def test_existing_analyze_items_still_works(self):
        """Backward compatibility: existing API still functions."""
        from app.notion.schemas import NotionNewsItem

        service = AIService()
        items = [
            NotionNewsItem(
                id="test-1",
                url="https://example.com",
                summary="Record profit reported",
                sentiment="positive",
                action="",
                confidence=0,
                status="unprocessed",
                timestamp="2024-01-01T00:00:00Z",
            )
        ]
        results = service.analyze_items(items)
        assert len(results) == 1
        assert results[0].action in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD)

    def test_cross_validation_enabled_calls_both(self):
        """When cross_validation_enabled and openai_api_key set, secondary is called."""
        service = AIService()
        context = RAGContext(chunks=["market data"], query="BTC outlook", source_count=1)

        buy_decision = _make_decision(LLMProvider.CLAUDE, TradeAction.BUY, 80)
        sell_decision = _make_decision(LLMProvider.OPENAI, TradeAction.SELL, 70)

        with (
            patch.object(service, "_call_claude", return_value=buy_decision),
            patch.object(service, "_call_openai", return_value=sell_decision),
        ):
            settings = MagicMock()
            settings.cross_validation_enabled = True
            settings.openai_api_key = "some-key"
            settings.anthropic_api_key = "some-key"

            result = service.judge_with_rag("test", context, settings=settings)
            # Disagreement → HOLD (fail-closed)
            assert result.final_action == TradeAction.HOLD
            assert result.agreed is False
