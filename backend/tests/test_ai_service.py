# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_ai_service.py

from datetime import datetime, timezone

import pytest

from app.ai.schemas import AIAnalysisResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.notion.schemas import NotionNewsItem


def _make_item(summary: str) -> NotionNewsItem:
    return NotionNewsItem(
        id="dummy-id",
        url="https://example.com/news",
        summary=summary,
    )


def test_ai_service_rule_based_buy():
    service = AIService()
    item = _make_item("The company reported record profit and strong growth.")
    result = service.analyze_items([item])[0]

    assert result.action == TradeAction.BUY
    assert result.confidence >= 40
    assert result.sentiment == "positive"


def test_ai_service_rule_based_sell():
    service = AIService()
    item = _make_item("The company faces a major fraud scandal and bankruptcy risk.")
    result = service.analyze_items([item])[0]

    assert result.action == TradeAction.SELL
    assert result.confidence >= 40
    assert result.sentiment == "negative"


def test_ai_service_rule_based_hold_for_neutral_news():
    service = AIService()
    item = _make_item("The company announced a regular update with minor changes.")
    result = service.analyze_items([item])[0]

    # 中立ニュースなので HOLD を期待
    assert result.action == TradeAction.HOLD
    assert 0 <= result.confidence <= 100


def test_ai_service_uses_llm_analyzer_when_provided():
    # ダミーの LLMAnalyzer を用意し、BUY 判定を返すようにする
    def fake_llm_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="dummy-id",
            url="https://example.com/news",
            action=TradeAction.BUY,
            confidence=90,
            sentiment="positive",
            summary="LLM summary",
            reason="LLM reason",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=fake_llm_analyzer)
    item = _make_item("内容は何でもよい")
    result = service.analyze_items([item])[0]

    # LLM の結果がそのまま反映されていることを確認
    assert result.action == TradeAction.BUY
    assert result.confidence == 90
    assert result.sentiment == "positive"


@pytest.mark.vcr()
def test_judge_with_rag_vcr():
    """VCR カセットを使って judge_with_rag() が BUY/SELL/HOLD を返すことを確認。"""
    service = AIService()
    rag_context = RAGContext(
        chunks=["Bitcoin price surged 10% on strong institutional demand."],
        query="BTC price analysis",
        source_count=1,
    )
    result = service.judge_with_rag("BTC price analysis", rag_context)
    assert result.final_action in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD)
    assert 0 <= result.final_confidence <= 100


def test_build_rag_prompt_v3_without_market_context():
    """v3 テンプレートで market_context が None の場合に KeyError が起きないこと。

    AI_PROMPT_VERSION=v3 かつ market_context 未指定でスケジューラーが呼ぶパターン。
    """
    from unittest.mock import MagicMock

    from app.ai.config import AISettings

    service = AIService()
    rag_context = RAGContext(chunks=["test chunk"], query="test query", source_count=1)

    settings = MagicMock(spec=AISettings)
    settings.prompt_version = "v3"
    settings.anthropic_api_key = None  # API呼び出しは行わない
    settings.openai_api_key = None
    settings.cross_validation_enabled = False
    settings.shadow_mode = False

    # _build_rag_prompt が KeyError を起こさないことを確認（戻り値の形式だけ検証）
    system_prompt, user_content = service._build_rag_prompt(
        query="test query",
        rag_context=rag_context,
        version="v3",
        market_context=None,
    )
    assert isinstance(system_prompt, str)
    assert isinstance(user_content, str)
    assert "No agent signals available" in user_content
    assert "test chunk" in user_content
