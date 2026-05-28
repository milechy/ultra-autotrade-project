# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for data_feeds/finance_feed.py — Perplexity Finance feed parsing.

Covers the 2026-05-18 fix for pydantic ValidationError when Perplexity API
returns key_indicators as list[dict] instead of list[str].
"""

import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
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


# ---------------------------------------------------------------------------
# 2026-05-28: Retry + body logging on transient 4xx/5xx (Asana 1215189378837169)
# ---------------------------------------------------------------------------


def _make_status_response(status_code: int, body: str = "") -> MagicMock:
    """Build a mock httpx.Response with given status_code/text."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


@pytest.mark.asyncio
async def test_fetch_finance_data_retries_on_400_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200/400 交互 staging soak の再現: 1回目 400 → retry で 200 → 安定取得。"""
    # 1回目 400 (transient), 2回目 200
    bad_resp = _make_status_response(400, body='{"error":{"message":"upstream search timeout"}}')

    good_resp = MagicMock(spec=httpx.Response)
    good_resp.status_code = 200
    good_resp.raise_for_status = MagicMock()
    good_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "macro_summary": "FED holds.",
                            "fed_stance": "hawkish",
                            "stablecoin_risk": "low",
                            "key_indicators": ["FED: 5.25%"],
                        }
                    )
                }
            }
        ],
        "citations": ["https://fed.gov"],
    }

    monkeypatch.setattr("app.data_feeds.finance_feed._PERPLEXITY_RETRY_BACKOFF_SECONDS", 0.0)

    call_count = {"n": 0}

    async def fake_post(*_args: object, **_kwargs: object) -> MagicMock:
        call_count["n"] += 1
        return bad_resp if call_count["n"] == 1 else good_resp

    with patch("httpx.AsyncClient.post", new=fake_post):
        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    assert call_count["n"] == 2, "retry should fire exactly once after 400"
    assert result.fed_stance == "hawkish"
    assert result.updated_at is not None
    assert "API error" not in result.macro_summary


@pytest.mark.asyncio
async def test_fetch_finance_data_logs_body_on_persistent_400(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DoD: 400 のレスポンス body をログに残す (現状は status code only)。"""
    bad_body = '{"error":{"message":"model sonar-pro not available","type":"invalid_request"}}'
    bad_resp = _make_status_response(400, body=bad_body)

    monkeypatch.setattr("app.data_feeds.finance_feed._PERPLEXITY_RETRY_BACKOFF_SECONDS", 0.0)

    async def fake_post(*_args: object, **_kwargs: object) -> MagicMock:
        return bad_resp

    with patch("httpx.AsyncClient.post", new=fake_post):
        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                with caplog.at_level(logging.WARNING, logger="app.data_feeds.finance_feed"):
                    result = await fetch_finance_data(client)

    # 真因が判別できるレベルで body が記録される
    assert any(bad_body[:50] in rec.getMessage() for rec in caplog.records), (
        "non-2xx response body must appear in logs"
    )
    assert "400" in result.macro_summary or "error" in result.macro_summary.lower()
    assert result.updated_at is None


@pytest.mark.asyncio
async def test_fetch_finance_data_does_not_retry_on_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 (auth) は key 違いの本質的エラーで retry 無駄打ち → 1回で終わる。"""
    bad_resp = _make_status_response(401, body='{"error":{"message":"invalid api key"}}')

    monkeypatch.setattr("app.data_feeds.finance_feed._PERPLEXITY_RETRY_BACKOFF_SECONDS", 0.0)

    call_count = {"n": 0}

    async def fake_post(*_args: object, **_kwargs: object) -> MagicMock:
        call_count["n"] += 1
        return bad_resp

    with patch("httpx.AsyncClient.post", new=fake_post):
        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                await fetch_finance_data(client)

    assert call_count["n"] == 1, "auth errors must not be retried"


@pytest.mark.asyncio
async def test_fetch_finance_data_retries_on_timeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """httpx.TimeoutException も一過性として 1 回 retry。"""
    good_resp = MagicMock(spec=httpx.Response)
    good_resp.status_code = 200
    good_resp.raise_for_status = MagicMock()
    good_resp.json.return_value = {
        "choices": [{"message": {"content": "{}"}}],
        "citations": [],
    }

    monkeypatch.setattr("app.data_feeds.finance_feed._PERPLEXITY_RETRY_BACKOFF_SECONDS", 0.0)

    call_count = {"n": 0}

    async def fake_post(*_args: object, **_kwargs: object) -> MagicMock:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.TimeoutException("read timeout")
        return good_resp

    with patch("httpx.AsyncClient.post", new=fake_post):
        async with httpx.AsyncClient() as client:
            with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"}):
                result = await fetch_finance_data(client)

    assert call_count["n"] == 2
    assert result.updated_at is not None


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
