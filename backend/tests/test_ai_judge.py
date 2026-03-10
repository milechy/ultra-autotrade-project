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


class TestCallClaude:
    def test_call_claude_no_api_key_returns_hold(self):
        service = AIService()
        settings = MagicMock()
        settings.anthropic_api_key = None

        result = service._call_claude("test prompt", settings)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 0
        assert result.provider == LLMProvider.CLAUDE

    def test_call_claude_success(self):
        service = AIService()
        settings = MagicMock()
        settings.anthropic_api_key = "sk-test"
        settings.claude_model = "claude-sonnet-4-20250514"

        mock_anthropic_module = MagicMock()
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = '{"action":"BUY","confidence":80,"reason":"bullish"}'
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_module.Anthropic.return_value = mock_client

        import sys

        with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}):
            result = service._call_claude("test prompt", settings)
        assert result.action == TradeAction.BUY
        assert result.confidence == 80
        assert result.provider == LLMProvider.CLAUDE

    def test_call_claude_api_error_returns_hold(self):
        service = AIService()
        settings = MagicMock()
        settings.anthropic_api_key = "sk-test"
        settings.claude_model = "claude-sonnet-4-20250514"

        mock_anthropic_module = MagicMock()
        mock_anthropic_module.Anthropic.side_effect = Exception("Connection refused")

        import sys

        with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}):
            result = service._call_claude("test prompt", settings)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 0
        assert result.provider == LLMProvider.CLAUDE

    def test_call_claude_response_block_without_text_attr(self):
        """Block without text attribute → raw_text stays empty → parse error → HOLD."""
        service = AIService()
        settings = MagicMock()
        settings.anthropic_api_key = "sk-test"
        settings.claude_model = "claude-sonnet-4-20250514"

        mock_anthropic_module = MagicMock()
        mock_client = MagicMock()
        mock_block = MagicMock(spec=[])  # no attributes at all
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_module.Anthropic.return_value = mock_client

        import sys

        with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}):
            result = service._call_claude("test prompt", settings)
        # empty string → JSON parse fails → HOLD
        assert result.action == TradeAction.HOLD
        assert result.provider == LLMProvider.CLAUDE


class TestCallOpenAI:
    def test_call_openai_no_api_key_returns_hold(self):
        service = AIService()
        settings = MagicMock()
        settings.openai_api_key = None

        result = service._call_openai("test prompt", settings)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 0
        assert result.provider == LLMProvider.OPENAI

    def test_call_openai_success(self):
        service = AIService()
        settings = MagicMock()
        settings.openai_api_key = "sk-test"
        settings.openai_model = "gpt-4o"

        mock_openai_module = MagicMock()
        mock_openai_cls = MagicMock()
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = '{"action":"SELL","confidence":70,"reason":"bearish"}'
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai_cls.return_value = mock_client
        mock_openai_module.OpenAI = mock_openai_cls

        import sys

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            result = service._call_openai("test prompt", settings)
        assert result.action == TradeAction.SELL
        assert result.confidence == 70
        assert result.provider == LLMProvider.OPENAI

    def test_call_openai_api_error_returns_hold(self):
        service = AIService()
        settings = MagicMock()
        settings.openai_api_key = "sk-test"
        settings.openai_model = "gpt-4o"

        mock_openai_module = MagicMock()
        mock_openai_cls = MagicMock()
        mock_openai_cls.side_effect = Exception("API quota exceeded")
        mock_openai_module.OpenAI = mock_openai_cls

        import sys

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            result = service._call_openai("test prompt", settings)
        assert result.action == TradeAction.HOLD
        assert result.confidence == 0
        assert result.provider == LLMProvider.OPENAI

    def test_call_openai_none_content_returns_hold(self):
        """When message.content is None, parse error → HOLD."""
        service = AIService()
        settings = MagicMock()
        settings.openai_api_key = "sk-test"
        settings.openai_model = "gpt-4o"

        mock_openai_module = MagicMock()
        mock_openai_cls = MagicMock()
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = None
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai_cls.return_value = mock_client
        mock_openai_module.OpenAI = mock_openai_cls

        import sys

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            result = service._call_openai("test prompt", settings)
        assert result.action == TradeAction.HOLD
        assert result.provider == LLMProvider.OPENAI


class TestAnalyzeSingleWithLLMAnalyzer:
    def test_analyze_single_llm_analyzer_success(self):
        """_analyze_single uses llm_analyzer when provided and it succeeds."""
        from datetime import datetime, timezone

        from app.notion.schemas import NotionNewsItem

        item = NotionNewsItem(
            id="item-1",
            url="https://example.com/news/1",
            summary="Record profits reported by crypto firms",
            sentiment=None,
            action=None,
            confidence=None,
            status="unprocessed",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        def fake_analyzer(news_item: NotionNewsItem):
            from datetime import datetime, timezone

            from app.ai.schemas import AIAnalysisResult, TradeAction

            return AIAnalysisResult(
                id=news_item.id,
                url=news_item.url,
                action=TradeAction.BUY,
                confidence=90,
                sentiment="positive",
                summary="Test summary",
                reason="Strong buy signal",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )

        service = AIService(llm_analyzer=fake_analyzer)
        result = service._analyze_single(item)
        assert result.action == TradeAction.BUY
        assert result.confidence == 90

    def test_analyze_single_llm_analyzer_exception_falls_back_to_rule_based(self):
        """When llm_analyzer raises, _analyze_single falls back to rule-based."""
        from datetime import datetime, timezone

        from app.notion.schemas import NotionNewsItem

        item = NotionNewsItem(
            id="item-2",
            url="https://example.com/news/bullish-news",
            summary="record profit announced",
            sentiment=None,
            action=None,
            confidence=None,
            status="unprocessed",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        def failing_analyzer(news_item: NotionNewsItem):
            raise RuntimeError("LLM unavailable")

        service = AIService(llm_analyzer=failing_analyzer)
        result = service._analyze_single(item)
        # Falls back to rule-based: "record profit" → BUY
        assert result.action == TradeAction.BUY

    def test_analyze_single_no_llm_uses_now_default(self):
        """When now is None, _analyze_single uses current UTC time."""
        from app.notion.schemas import NotionNewsItem

        item = NotionNewsItem(
            id="item-3",
            url="https://example.com",
            summary="neutral market conditions",
            sentiment=None,
            action=None,
            confidence=None,
            status="unprocessed",
            timestamp=None,
        )

        service = AIService()
        result = service._analyze_single(item, now=None)
        assert result.action == TradeAction.HOLD  # neutral → HOLD


# ------------------------------------------------------------------ #
# TestPromptVersioning                                                 #
# ------------------------------------------------------------------ #


class TestPromptVersioning:
    """プロンプトバージョン管理のテスト。"""

    def test_get_prompt_template_v1(self):
        from app.ai.prompts import get_prompt_template

        tmpl = get_prompt_template("v1")
        assert tmpl.version == "v1"
        assert "BUY" in tmpl.system_prompt

    def test_get_prompt_template_v2(self):
        from app.ai.prompts import get_prompt_template

        tmpl = get_prompt_template("v2")
        assert tmpl.version == "v2"
        assert tmpl.description != ""

    def test_unknown_version_falls_back_to_v1(self):
        from app.ai.prompts import get_prompt_template

        tmpl = get_prompt_template("v99")
        assert tmpl.version == "v1"

    def test_list_versions(self):
        from app.ai.prompts import list_versions

        versions = list_versions()
        assert "v1" in versions
        assert "v2" in versions

    def test_prompt_version_default_in_llm_decision(self):
        from app.ai.schemas import LLMDecision, LLMProvider, TradeAction

        decision = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.HOLD,
            confidence=0,
            reason="no key",
        )
        assert decision.prompt_version == "v1"

    def test_prompt_version_custom_in_llm_decision(self):
        from app.ai.schemas import LLMDecision, LLMProvider, TradeAction

        decision = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.BUY,
            confidence=80,
            reason="test",
            prompt_version="v2",
        )
        assert decision.prompt_version == "v2"

    def test_judge_with_rag_propagates_prompt_version(self):
        """judge_with_rag() がAPIキー未設定でもprompt_versionをレスポンスに含める。"""
        from unittest.mock import MagicMock

        from app.ai.config import AISettings
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService

        service = AIService()
        rag_context = RAGContext(chunks=["BTC up 10%"], query="BTC analysis", source_count=1)

        settings = MagicMock(spec=AISettings)
        settings.anthropic_api_key = None
        settings.openai_api_key = None
        settings.cross_validation_enabled = False
        settings.prompt_version = "v2"
        settings.shadow_mode = False

        result = service.judge_with_rag("BTC analysis", rag_context, settings=settings)
        assert result.prompt_version == "v2"
        assert result.primary.prompt_version == "v2"

    def test_settings_default_prompt_version(self):
        """get_ai_settings() のデフォルトは v1。"""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_PROMPT_VERSION", None)
            from app.ai.config import get_ai_settings

            settings = get_ai_settings()
        assert settings.prompt_version == "v1"

    def test_settings_custom_prompt_version(self):
        """AI_PROMPT_VERSION=v2 を設定すると v2 になる。"""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"AI_PROMPT_VERSION": "v2"}):
            from app.ai.config import get_ai_settings

            settings = get_ai_settings()
        assert settings.prompt_version == "v2"
