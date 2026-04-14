# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for MMT Market Data API feed module."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.data_feeds.mmt_feed as mmt_module
from app.data_feeds.mmt_feed import (
    MMTCandle,
    MMTData,
    MMTOpenInterest,
    MMTStats,
    fetch_mmt_candles,
    fetch_mmt_data,
    fetch_mmt_oi,
    fetch_mmt_stats,
    get_cached_mmt_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(json_response: dict) -> AsyncMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = json_response
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    return client


def _make_http_error_client(status_code: int = 429) -> AsyncMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        str(status_code), request=MagicMock(), response=mock_resp
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    return client


# ---------------------------------------------------------------------------
# Test MMTData.to_prompt_section
# ---------------------------------------------------------------------------


class TestMMTDataToPromptSection:
    def test_empty_data_returns_empty_string(self) -> None:
        data = MMTData()
        assert data.to_prompt_section() == ""

    def test_stats_and_oi_generates_section(self) -> None:
        data = MMTData(
            stats=[
                MMTStats(
                    symbol="btc/usd",
                    exchange="binancef",
                    funding_rate=Decimal("0.000125"),
                )
            ],
            open_interest=[
                MMTOpenInterest(
                    symbol="btc/usd",
                    exchange="binancef",
                    open_interest=Decimal("12500000000"),
                    oi_change_pct=3.2,
                )
            ],
        )
        section = data.to_prompt_section()
        assert "## MMT Market Data" in section
        assert "btc/usd Funding Rate" in section
        assert "ロング過多" in section
        assert "btc/usd OI" in section
        assert "+3.20%" in section

    def test_negative_funding_rate_shows_short_heavy(self) -> None:
        data = MMTData(
            stats=[
                MMTStats(
                    symbol="eth/usd",
                    exchange="binancef",
                    funding_rate=Decimal("-0.000050"),
                )
            ],
        )
        section = data.to_prompt_section()
        assert "ショート過多" in section

    def test_zero_funding_rate_shows_neutral(self) -> None:
        data = MMTData(
            stats=[
                MMTStats(
                    symbol="btc/usd",
                    exchange="binancef",
                    funding_rate=Decimal("0"),
                )
            ],
        )
        section = data.to_prompt_section()
        assert "中立" in section

    def test_none_funding_rate_excluded(self) -> None:
        data = MMTData(
            stats=[MMTStats(symbol="btc/usd", exchange="binancef", funding_rate=None)],
        )
        # stats exists but funding_rate is None → no line added → only header → empty
        assert data.to_prompt_section() == ""

    def test_oi_without_change_pct(self) -> None:
        data = MMTData(
            open_interest=[
                MMTOpenInterest(
                    symbol="btc/usd",
                    exchange="binancef",
                    open_interest=Decimal("5000000000"),
                    oi_change_pct=None,
                )
            ],
        )
        section = data.to_prompt_section()
        assert "btc/usd OI" in section
        assert "変化率" not in section


# ---------------------------------------------------------------------------
# Test fetch_mmt_stats
# ---------------------------------------------------------------------------


class TestFetchMMTStats:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        client = _make_client(
            {
                "data": [
                    {"fr": 0.000125, "bd": 1000000, "ad": 900000, "t": 1700000000},
                ]
            }
        )
        result = await fetch_mmt_stats(client, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.funding_rate == Decimal("0.000125")
        assert result.bid_depth_usd == Decimal("1000000")
        assert result.timestamp == 1700000000

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_stats(self) -> None:
        client = _make_client({"data": []})
        result = await fetch_mmt_stats(client, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.funding_rate is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self) -> None:
        client = _make_http_error_client()
        result = await fetch_mmt_stats(client, "test_key", "btc/usd", "binancef")
        assert result is None

    @pytest.mark.asyncio
    async def test_general_exception_returns_none(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=RuntimeError("connection refused"))
        result = await fetch_mmt_stats(client, "test_key", "btc/usd", "binancef")
        assert result is None


# ---------------------------------------------------------------------------
# Test fetch_mmt_oi
# ---------------------------------------------------------------------------


class TestFetchMMTOI:
    def setup_method(self) -> None:
        # Reset module-level _previous_oi between tests
        mmt_module._previous_oi.clear()

    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        client = _make_client({"data": [{"oi": 12500000000, "t": 1700000000}]})
        result = await fetch_mmt_oi(client, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.open_interest == Decimal("12500000000")
        assert result.timestamp == 1700000000

    @pytest.mark.asyncio
    async def test_no_previous_oi_change_pct_is_none(self) -> None:
        client = _make_client({"data": [{"oi": 10000000000, "t": 1700000000}]})
        result = await fetch_mmt_oi(client, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.oi_change_pct is None

    @pytest.mark.asyncio
    async def test_oi_change_pct_calculated_on_second_call(self) -> None:
        # First call — establishes baseline
        client1 = _make_client({"data": [{"oi": 10000000000, "t": 1700000000}]})
        await fetch_mmt_oi(client1, "test_key", "btc/usd", "binancef")

        # Second call — 10% increase
        client2 = _make_client({"data": [{"oi": 11000000000, "t": 1700003600}]})
        result = await fetch_mmt_oi(client2, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.oi_change_pct is not None
        assert abs(result.oi_change_pct - 10.0) < 0.01

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_oi(self) -> None:
        client = _make_client({"data": []})
        result = await fetch_mmt_oi(client, "test_key", "btc/usd", "binancef")
        assert result is not None
        assert result.open_interest is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self) -> None:
        client = _make_http_error_client()
        result = await fetch_mmt_oi(client, "test_key", "btc/usd", "binancef")
        assert result is None


# ---------------------------------------------------------------------------
# Test fetch_mmt_candles
# ---------------------------------------------------------------------------


class TestFetchMMTCandles:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        client = _make_client(
            {
                "data": [
                    {"o": 60000, "h": 61000, "l": 59000, "c": 60500, "v": 1234, "t": 1700000000},
                    {"o": 60500, "h": 62000, "l": 60000, "c": 61000, "v": 2345, "t": 1700003600},
                ]
            }
        )
        candles = await fetch_mmt_candles(client, "test_key", "btc/usd", "binancef")
        assert len(candles) == 2
        assert isinstance(candles[0], MMTCandle)
        assert candles[0].open == Decimal("60000")
        assert candles[1].close == Decimal("61000")

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_list(self) -> None:
        client = _make_client({"data": []})
        candles = await fetch_mmt_candles(client, "test_key", "btc/usd", "binancef")
        assert candles == []

    @pytest.mark.asyncio
    async def test_api_error_returns_empty_list(self) -> None:
        client = _make_http_error_client()
        candles = await fetch_mmt_candles(client, "test_key", "btc/usd", "binancef")
        assert candles == []


# ---------------------------------------------------------------------------
# Test fetch_mmt_data (integration — settings + cache)
# ---------------------------------------------------------------------------


class TestFetchMMTData:
    def setup_method(self) -> None:
        mmt_module._cached_mmt = None
        mmt_module._previous_oi.clear()

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self) -> None:
        with patch.dict("os.environ", {"MMT_API_ENABLED": "false", "MMT_API_KEY": "key"}):
            result = await fetch_mmt_data()
        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self) -> None:
        with patch.dict("os.environ", {"MMT_API_ENABLED": "true", "MMT_API_KEY": ""}):
            result = await fetch_mmt_data()
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_api_key_env_returns_none(self) -> None:
        env = {"MMT_API_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=False):
            # Ensure MMT_API_KEY is absent
            import os

            os.environ.pop("MMT_API_KEY", None)
            result = await fetch_mmt_data()
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_fetch_updates_cache(self) -> None:
        stats_resp = {"data": [{"fr": 0.0001, "bd": None, "ad": None, "t": 1700000000}]}
        oi_resp = {"data": [{"oi": 10000000000, "t": 1700000000}]}
        candles_resp = {
            "data": [{"o": 60000, "h": 61000, "l": 59000, "c": 60500, "v": 100, "t": 1700000000}]
        }

        call_count = 0
        responses = [stats_resp, oi_resp, candles_resp, stats_resp, oi_resp, candles_resp]

        async def mock_get(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[call_count % len(responses)]
            call_count += 1
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", {"MMT_API_ENABLED": "true", "MMT_API_KEY": "test_key"}):
            with patch("app.data_feeds.mmt_feed.httpx.AsyncClient", return_value=mock_client):
                result = await fetch_mmt_data()

        assert result is not None
        assert isinstance(result, MMTData)
        assert result.fetched_at is not None
        # Cache was updated
        assert mmt_module._cached_mmt is result


# ---------------------------------------------------------------------------
# Test get_cached_mmt_data
# ---------------------------------------------------------------------------


class TestGetCachedMMTData:
    def setup_method(self) -> None:
        mmt_module._cached_mmt = None

    def test_returns_none_when_not_cached(self) -> None:
        assert get_cached_mmt_data() is None

    def test_returns_cached_data(self) -> None:
        data = MMTData()
        mmt_module._cached_mmt = data
        assert get_cached_mmt_data() is data


# ---------------------------------------------------------------------------
# Test MarketContext integration
# ---------------------------------------------------------------------------


class TestMarketContextMMTIntegration:
    def setup_method(self) -> None:
        mmt_module._cached_mmt = None

    def test_mmt_data_none_does_not_affect_existing_output(self) -> None:
        from app.data_feeds.context import build_market_context

        ctx = build_market_context()
        prompt = ctx.to_prompt_context()
        # Should still have existing geo risk section
        assert "Geopolitical Risk" in prompt
        # No MMT section when cache is None
        assert "MMT Market Data" not in prompt

    def test_mmt_data_present_adds_section(self) -> None:
        from app.data_feeds.context import build_market_context

        mmt = MMTData(
            stats=[
                MMTStats(
                    symbol="btc/usd",
                    exchange="binancef",
                    funding_rate=Decimal("0.0002"),
                )
            ],
        )
        mmt_module._cached_mmt = mmt

        ctx = build_market_context()
        prompt = ctx.to_prompt_context()
        assert "MMT Market Data" in prompt
        assert "btc/usd Funding Rate" in prompt
        assert "ロング過多" in prompt
