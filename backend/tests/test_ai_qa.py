# backend/tests/test_ai_qa.py

from datetime import datetime, timezone
from typing import List, Tuple

import pytest

from app.ai.schemas import AIAnalysisResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.notion.schemas import NotionNewsItem


def _make_item(summary: str, item_id: str = "dummy-id") -> NotionNewsItem:
    return NotionNewsItem(
        id=item_id,
        url="https://example.com/news",
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 20-item dataset: (summary, expected_action)
# ---------------------------------------------------------------------------
# BUY cases: strong positive news containing rule-based positive keywords
# SELL cases: strong negative news containing rule-based negative keywords
# HOLD cases: neutral/ambiguous news

DATASET: List[Tuple[str, TradeAction]] = [
    # --- BUY (8 items) ---
    ("Bitcoin ETF approval drives record profit for institutional investors.", TradeAction.BUY),
    ("Company reports record revenue beating all analyst expectations.", TradeAction.BUY),
    ("Ethereum shows bullish breakout above key resistance levels.", TradeAction.BUY),
    ("Analyst upgrade lifts crypto market amid bullish sentiment.", TradeAction.BUY),
    ("DeFi protocol posts record profit in Q3, attracting new investors.", TradeAction.BUY),
    ("Market shows bullish trend with profit grows quarter over quarter.", TradeAction.BUY),
    ("Institutional upgrade of crypto assets signals bullish outlook.", TradeAction.BUY),
    ("Token price surges after record revenue announcement this month.", TradeAction.BUY),
    # --- SELL (8 items) ---
    ("Major exchange hack results in $500M losses; bankruptcy risk rises.", TradeAction.SELL),
    ("SEC lawsuit targets leading crypto exchange over alleged fraud.", TradeAction.SELL),
    ("Crypto lender files for bankruptcy amid liquidity crisis.", TradeAction.SELL),
    ("Developer arrested in massive fraud case involving token sales.", TradeAction.SELL),
    ("Regulator downgrade warning triggers widespread panic selling.", TradeAction.SELL),
    ("Exchange faces lawsuit from customers claiming systematic fraud.", TradeAction.SELL),
    ("Stablecoin issuer faces bankruptcy risk due to reserve scandal.", TradeAction.SELL),
    ("Company confirms fraud investigation leading to downgrade by auditors.", TradeAction.SELL),
    # --- HOLD (4 items) ---
    ("Crypto market sees mixed signals with no clear direction.", TradeAction.HOLD),
    ("Weekly update: trading volumes remained stable with minor fluctuations.", TradeAction.HOLD),
    ("Company announced a regular update with minor changes in operations.", TradeAction.HOLD),
    ("Market observers note steady activity; no major catalysts expected.", TradeAction.HOLD),
]


def test_dataset_size():
    assert len(DATASET) == 20


def test_judgment_match_rate_80_percent():
    service = AIService()
    matched = 0
    for summary, expected in DATASET:
        item = _make_item(summary)
        result = service.analyze_items([item])[0]
        if result.action == expected:
            matched += 1
    match_rate = matched / len(DATASET)
    assert match_rate >= 0.80, (
        f"Match rate {match_rate:.2%} is below 80% ({matched}/{len(DATASET)})"
    )


# ---------------------------------------------------------------------------
# Specific BUY cases
# ---------------------------------------------------------------------------


def test_bitcoin_etf_approval_buy():
    service = AIService()
    item = _make_item("Bitcoin ETF approval drives record profit for institutional investors.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.BUY


def test_record_revenue_buy():
    service = AIService()
    item = _make_item("Company reports record revenue beating all analyst expectations.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.BUY


def test_bullish_breakout_buy():
    service = AIService()
    item = _make_item("Ethereum shows bullish breakout above key resistance levels.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.BUY


# ---------------------------------------------------------------------------
# Specific SELL cases
# ---------------------------------------------------------------------------


def test_exchange_hack_sell():
    service = AIService()
    item = _make_item("Major exchange hack results in $500M in losses; bankruptcy risk rises.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.SELL


def test_sec_lawsuit_sell():
    service = AIService()
    item = _make_item("SEC lawsuit targets leading crypto exchange over alleged fraud.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.SELL


def test_bankruptcy_sell():
    service = AIService()
    item = _make_item("Crypto lender files for bankruptcy amid liquidity crisis.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.SELL


# ---------------------------------------------------------------------------
# HOLD cases
# ---------------------------------------------------------------------------


def test_neutral_news_hold():
    service = AIService()
    item = _make_item("Crypto market sees mixed signals with no clear direction.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.HOLD


def test_ambiguous_news_hold():
    service = AIService()
    item = _make_item("Company announced a regular update with minor changes in operations.")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.HOLD


# ---------------------------------------------------------------------------
# Safety guard: confidence < 40 → HOLD regardless of signal
# ---------------------------------------------------------------------------


def test_safety_guard_low_confidence_becomes_hold():
    def low_confidence_buy(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="test-id",
            url="https://example.com",
            action=TradeAction.BUY,
            confidence=30,
            sentiment="positive",
            summary="low confidence BUY",
            reason="test",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=low_confidence_buy)
    item = _make_item("any news")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.HOLD
    assert result.confidence == 30


def test_safety_guard_confidence_39_becomes_hold():
    def borderline_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="test-id",
            url="https://example.com",
            action=TradeAction.SELL,
            confidence=39,
            sentiment="negative",
            summary="borderline",
            reason="test",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=borderline_analyzer)
    item = _make_item("any news")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.HOLD


def test_safety_guard_confidence_40_passes():
    def exactly_40_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="test-id",
            url="https://example.com",
            action=TradeAction.BUY,
            confidence=40,
            sentiment="positive",
            summary="exactly 40",
            reason="test",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=exactly_40_analyzer)
    item = _make_item("any news")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.BUY
    assert result.confidence == 40


# ---------------------------------------------------------------------------
# LLM analyzer override: inject custom analyzer and verify it's used
# ---------------------------------------------------------------------------


def test_llm_analyzer_override_buy():
    def fake_buy_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="override-id",
            url="https://example.com/llm",
            action=TradeAction.BUY,
            confidence=90,
            sentiment="positive",
            summary="LLM override summary",
            reason="LLM override reason",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=fake_buy_analyzer)
    item = _make_item("neutral content that rule-based would HOLD")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.BUY
    assert result.confidence == 90
    assert result.sentiment == "positive"


def test_llm_analyzer_override_sell():
    def fake_sell_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        return AIAnalysisResult(
            id="override-id",
            url="https://example.com/llm",
            action=TradeAction.SELL,
            confidence=85,
            sentiment="negative",
            summary="LLM sell summary",
            reason="LLM sell reason",
            timestamp=datetime.now(timezone.utc),
        )

    service = AIService(llm_analyzer=fake_sell_analyzer)
    item = _make_item("positive content that rule-based would BUY")
    result = service.analyze_items([item])[0]
    assert result.action == TradeAction.SELL
    assert result.confidence == 85


# ---------------------------------------------------------------------------
# Fallback: LLM fails → rule-based is used
# ---------------------------------------------------------------------------


def test_llm_failure_falls_back_to_rule_based_buy():
    def failing_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        raise RuntimeError("LLM API connection error")

    service = AIService(llm_analyzer=failing_analyzer)
    item = _make_item("Company reports record profit and bullish outlook.")
    result = service.analyze_items([item])[0]
    # Rule-based should pick up "record profit" and "bullish" → BUY
    assert result.action == TradeAction.BUY


def test_llm_failure_falls_back_to_rule_based_hold():
    def failing_analyzer(_: NotionNewsItem) -> AIAnalysisResult:
        raise ValueError("JSON parse error")

    service = AIService(llm_analyzer=failing_analyzer)
    item = _make_item("Nothing special about the market today.")
    result = service.analyze_items([item])[0]
    # Rule-based should return HOLD for neutral content
    assert result.action == TradeAction.HOLD


# ---------------------------------------------------------------------------
# VCR: judge_with_rag
# ---------------------------------------------------------------------------


@pytest.mark.vcr()
def test_judge_with_rag_vcr():
    """VCR カセットを使って judge_with_rag() が BUY/SELL/HOLD を返すことを確認。"""
    service = AIService()
    rag_context = RAGContext(
        chunks=["Bitcoin ETF approved; institutional demand surges to record profit levels."],
        query="BTC ETF approval impact",
        source_count=1,
    )
    result = service.judge_with_rag("BTC ETF approval impact", rag_context)
    assert result.final_action in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD)
    assert 0 <= result.final_confidence <= 100
