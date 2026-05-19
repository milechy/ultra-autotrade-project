# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for data_feeds/finance_feed.py — Perplexity Finance feed parsing.

Covers the 2026-05-18 fix for pydantic ValidationError when Perplexity API
returns key_indicators as list[dict] instead of list[str].
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-finance-feed-key")

from app.data_feeds.finance_feed import FinanceFeedResult, fetch_finance_data  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests: FinanceFeedResult construction
# ---------------------------------------------------------------------------


def test_finance_feed_result_string_indicators() -> None:
    """key_indicators as list[str] — standard case."""
    result = FinanceFeedResult(
        macro_summary="Stable macro.",
        fed_stance="neutral",
        stablecoin_risk="low",
        key_indicators=["CPI: 3.2%", "FED rate: 5.25%"],
    )
    assert result.key_indicators == ["CPI: 3.2%", "FED rate: 5.25%"]
    assert result.fed_stance == "neutral"


def test_finance_feed_result_defaults() -> None:
    """Default FinanceFeedResult has sensible fallbacks."""
    result = FinanceFeedResult()
    assert "available" in result.macro_summary.lower() or result.macro_summary != ""
    assert result.fed_stance == "unknown"
    assert result.stablecoin_risk == "low"
    assert result.key_indicators == []
    assert result.sources_count == 0
    assert result.updated_at is None


# ---------------------------------------------------------------------------
# Integration tests: fetch_finance_data with mocked httpx
# ---------------------------------------------------------------------------


def _make_mock_response(content: str, citations: list | None = None) -> MagicMock:
    """Build a mock httpx response with Perplexity-style JSON payload."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "citations": citations or [],
    }
    return mock_resp


@pytest.mark.asyncio
async def test_fetch_finance_data_list_of_strings() -> None:
    """Perplexity returns key_indicators as list[str] — parses without error."""
    payload = {
        "macro_summary": "FED holds rates steady.",
        "fed_stance": "neutral",
        "stablecoin_risk": "low",
        "key_indicators": ["CPI: 3.2%", "FED: 5.25%", "USDC reserve: $43B"],
    }
    mock_resp = _make_mock_response(json.dumps(payload), citations=["https://example.com"])

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        import httpx

        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    assert result.fed_stance == "neutral"
    assert result.stablecoin_risk == "low"
    assert result.key_indicators == ["CPI: 3.2%", "FED: 5.25%", "USDC reserve: $43B"]
    assert result.sources_count == 1
    assert result.updated_at is not None


@pytest.mark.asyncio
async def test_fetch_finance_data_list_of_dicts() -> None:
    """Regression: Perplexity returns key_indicators as list[dict].

    Before the 2026-05-18 fix, this caused pydantic ValidationError and
    the finance feed always fell back to 'Finance data fetch failed.'
    """
    payload = {
        "macro_summary": "DeFi market conditions are mixed.",
        "fed_stance": "hawkish",
        "stablecoin_risk": "medium",
        "key_indicators": [
            {"name": "USDT + USDC market cap", "value": "$155B pass-through to holders."},
            {"name": "FED rate", "value": "5.25%-5.50%"},
            {"indicator": "Aave / DeFi activity", "description": "incentive-heavy promotions"},
        ],
    }
    mock_resp = _make_mock_response(json.dumps(payload))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        import httpx

        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    # Must not fall back to error message
    assert "failed" not in result.macro_summary.lower()
    assert result.fed_stance == "hawkish"
    assert result.stablecoin_risk == "medium"
    assert result.updated_at is not None

    # key_indicators should be coerced to strings
    assert len(result.key_indicators) == 3
    for indicator in result.key_indicators:
        assert isinstance(indicator, str), f"Expected str, got {type(indicator)}: {indicator}"

    # Verify format: "name: value" for dicts with name+value
    assert "USDT + USDC market cap" in result.key_indicators[0]
    assert "FED rate" in result.key_indicators[1]


@pytest.mark.asyncio
async def test_fetch_finance_data_no_api_key() -> None:
    """Missing PERPLEXITY_API_KEY returns default result without error."""
    import httpx

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PERPLEXITY_API_KEY", None)
        async with httpx.AsyncClient() as client:
            result = await fetch_finance_data(client)

    assert isinstance(result, FinanceFeedResult)
    assert "not configured" in result.macro_summary.lower()


@pytest.mark.asyncio
async def test_fetch_finance_data_invalid_json() -> None:
    """Malformed JSON response falls back gracefully."""
    mock_resp = _make_mock_response("not valid json")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        import httpx

        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    assert isinstance(result, FinanceFeedResult)
    # Falls back to raw content as macro_summary
    assert "not valid json" in result.macro_summary


@pytest.mark.asyncio
async def test_fetch_finance_data_mixed_indicator_types() -> None:
    """key_indicators with mixed str and dict items — all coerced to str."""
    payload = {
        "macro_summary": "Mixed indicator format.",
        "fed_stance": "dovish",
        "stablecoin_risk": "low",
        "key_indicators": [
            "CPI: 3.1%",
            {"name": "FED rate", "value": "4.75%"},
            "BTC dominance: 55%",
        ],
    }
    mock_resp = _make_mock_response(json.dumps(payload))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        import httpx

        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    assert len(result.key_indicators) == 3
    for item in result.key_indicators:
        assert isinstance(item, str)
    assert result.key_indicators[0] == "CPI: 3.1%"
    assert "FED rate" in result.key_indicators[1]
    assert result.key_indicators[2] == "BTC dominance: 55%"
