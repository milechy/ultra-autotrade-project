# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for Perplexity Finance feed module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.data_feeds.finance_feed import (
    FinanceFeedResult,
    fetch_finance_data,
    get_cached_finance,
)


class TestFinanceFeedSchemas:
    def test_default_result(self) -> None:
        result = FinanceFeedResult()
        assert result.fed_stance == "unknown"
        assert result.stablecoin_risk == "low"
        assert result.key_indicators == []

    def test_cached_default(self) -> None:
        result = get_cached_finance()
        assert "No finance data" in result.macro_summary


class TestFetchFinanceData:
    @pytest.mark.asyncio
    async def test_no_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            async with httpx.AsyncClient() as client:
                result = await fetch_finance_data(client)
        assert "not configured" in result.macro_summary

    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "macro_summary": "FED maintains hawkish stance. CPI at 3.2%. DeFi yields stable.",
                                "fed_stance": "hawkish",
                                "stablecoin_risk": "low",
                                "key_indicators": [
                                    "FED funds rate: 5.25-5.50%",
                                    "CPI: 3.2% YoY",
                                    "USDC reserves: $32.1B (fully backed)",
                                ],
                            }
                        )
                    }
                }
            ],
            "citations": ["https://fed.gov/1", "https://sec.gov/2"],
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_finance_data(mock_client)

        assert result.fed_stance == "hawkish"
        assert result.stablecoin_risk == "low"
        assert len(result.key_indicators) == 3
        assert result.sources_count == 2
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_invalid_enum_values_default(self) -> None:
        """Invalid fed_stance/stablecoin_risk values fall back to defaults."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "macro_summary": "Markets uncertain.",
                                "fed_stance": "confused",
                                "stablecoin_risk": "extreme",
                            }
                        )
                    }
                }
            ],
            "citations": [],
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_finance_data(mock_client)

        assert result.fed_stance == "unknown"
        assert result.stablecoin_risk == "low"

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Macro conditions are stable overall."}}],
            "citations": ["https://example.com"],
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_finance_data(mock_client)

        assert "stable" in result.macro_summary
        assert result.sources_count == 1

    @pytest.mark.asyncio
    async def test_http_error_fallback(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=mock_response
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            result = await fetch_finance_data(mock_client)

        assert "429" in result.macro_summary or "error" in result.macro_summary.lower()
