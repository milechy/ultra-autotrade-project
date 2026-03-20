# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for Perplexity news feed module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.data_feeds.news_feed import (
    NewsFeedResult,
    fetch_crypto_news,
    get_cached_news,
)


class TestNewsFeedSchemas:
    def test_default_result(self) -> None:
        result = NewsFeedResult()
        assert result.sentiment == "neutral"
        assert "No news" in result.summary
        assert result.key_events == []
        assert result.sources_count == 0

    def test_cached_default(self) -> None:
        result = get_cached_news()
        assert result.sentiment == "neutral"


class TestFetchCryptoNews:
    @pytest.mark.asyncio
    async def test_no_api_key(self) -> None:
        """Without API key, returns graceful fallback."""
        with patch.dict("os.environ", {}, clear=True):
            async with httpx.AsyncClient() as client:
                result = await fetch_crypto_news(client)
        assert "not configured" in result.summary

    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        """Mocked successful Perplexity response with JSON body."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "ETH rallied 5% on FED rate cut signals.",
                                "sentiment": "positive",
                                "key_events": [
                                    "FED signals rate cut",
                                    "Aave TVL reaches $20B",
                                    "USDC regains peg confidence",
                                ],
                            }
                        )
                    }
                }
            ],
            "citations": ["https://coindesk.com/1", "https://theblock.co/2"],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_crypto_news(mock_client)

        assert result.sentiment == "positive"
        assert "ETH" in result.summary or "FED" in result.summary
        assert len(result.key_events) == 3
        assert result.sources_count == 2
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self) -> None:
        """Non-JSON response falls back to raw text."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Just plain text about crypto markets."}}],
            "citations": [],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_crypto_news(mock_client)

        assert "plain text" in result.summary
        assert result.sentiment == "neutral"
        assert result.key_events == []

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self) -> None:
        """JSON wrapped in markdown code fences is parsed correctly."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"summary": "Market stable.", "sentiment": "neutral", "key_events": ["No major events"]}\n```'
                    }
                }
            ],
            "citations": [],
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_crypto_news(mock_client)

        assert result.sentiment == "neutral"
        assert "Market stable" in result.summary

    @pytest.mark.asyncio
    async def test_http_error_fallback(self) -> None:
        """HTTP error returns graceful fallback, does not raise."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_crypto_news(mock_client)

        assert "429" in result.summary or "error" in result.summary.lower()