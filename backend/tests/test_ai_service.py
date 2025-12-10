# backend/tests/test_ai_service.py

from datetime import datetime, timezone

from app.ai.schemas import AIAnalysisResult, TradeAction
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

