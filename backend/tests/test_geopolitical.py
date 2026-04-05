# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for geopolitical risk feed module."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.data_feeds.geopolitical import (
    GDELTEvent,
    GeoRiskResult,
    USGSEarthquake,
    calculate_geo_risk_score,
    get_cached_geo_risk,
)


class TestGeoRiskScoreCalculator:
    """Test the risk score calculator."""

    def test_stable_conditions(self):
        """Stable: positive tone, few events, no earthquakes."""
        gdelt = GDELTEvent(avg_tone=Decimal("3.0"), event_count=50)
        result = calculate_geo_risk_score(gdelt, [])
        assert result.geo_risk_score < 20
        assert "stable" in result.summary.lower()

    def test_elevated_conflict(self):
        """Elevated: negative tone, many conflict events."""
        gdelt = GDELTEvent(avg_tone=Decimal("-8.0"), event_count=400)
        result = calculate_geo_risk_score(gdelt, [])
        assert result.geo_risk_score >= 40
        assert any(word in result.summary.lower() for word in ("conflict", "events", "tension"))

    def test_extreme_with_earthquake(self):
        """Extreme: very negative tone + major earthquake."""
        gdelt = GDELTEvent(avg_tone=Decimal("-12.0"), event_count=600)
        quakes = [USGSEarthquake(magnitude=Decimal("7.5"), location="Pacific Ocean")]
        result = calculate_geo_risk_score(gdelt, quakes)
        assert result.geo_risk_score >= 80
        assert result.max_earthquake_magnitude == Decimal("7.5")

    def test_earthquake_only(self):
        """Large earthquake but otherwise stable."""
        gdelt = GDELTEvent(avg_tone=Decimal("2.0"), event_count=30)
        quakes = [USGSEarthquake(magnitude=Decimal("6.5"), location="Japan")]
        result = calculate_geo_risk_score(gdelt, quakes)
        assert 20 <= result.geo_risk_score <= 40
        assert result.earthquake_count == 1

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        gdelt = GDELTEvent(avg_tone=Decimal("-15.0"), event_count=1000)
        quakes = [USGSEarthquake(magnitude=Decimal("8.0"), location="Global")]
        result = calculate_geo_risk_score(gdelt, quakes)
        assert result.geo_risk_score <= 100

    def test_default_cache(self):
        """Default cache returns safe fallback."""
        result = get_cached_geo_risk()
        assert 0 <= result.geo_risk_score <= 100
        assert result.summary != ""


class TestGeoRiskSchemas:
    """Test schema validation."""

    def test_geo_risk_result_bounds(self):
        """Score must be 0-100."""
        result = GeoRiskResult(geo_risk_score=50)
        assert 0 <= result.geo_risk_score <= 100

    def test_decimal_fields(self):
        """Decimal fields store correctly."""
        result = GeoRiskResult(
            gdelt_tone=Decimal("3.14"),
            max_earthquake_magnitude=Decimal("6.5"),
        )
        assert result.gdelt_tone == Decimal("3.14")
        assert result.max_earthquake_magnitude == Decimal("6.5")

    def test_multiple_earthquakes_max_magnitude(self):
        """Max magnitude is correctly identified from multiple quakes."""
        gdelt = GDELTEvent(avg_tone=Decimal("0"), event_count=0)
        quakes = [
            USGSEarthquake(magnitude=Decimal("5.2"), location="A"),
            USGSEarthquake(magnitude=Decimal("6.8"), location="B"),
            USGSEarthquake(magnitude=Decimal("5.9"), location="C"),
        ]
        result = calculate_geo_risk_score(gdelt, quakes)
        assert result.max_earthquake_magnitude == Decimal("6.8")
        assert result.earthquake_count == 3


class TestMarketContext:
    """Test the aggregated market context."""

    def test_build_context_defaults(self):
        """Default context has geo_risk, other fields are None."""
        from app.data_feeds.context import build_market_context

        ctx = build_market_context()
        assert ctx.geo_risk is not None
        assert ctx.aave_utilization_rate is None

    def test_build_context_with_aave_data(self):
        """Aave fields are included when provided."""
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            aave_utilization_rate=Decimal("87.5"),
            aave_supply_apy=Decimal("3.2"),
            health_factor=Decimal("1.72"),
        )
        assert ctx.aave_utilization_rate == Decimal("87.5")
        prompt = ctx.to_prompt_context()
        assert "87.5" in prompt
        assert "Geopolitical Risk" in prompt

    def test_prompt_context_includes_news(self):
        """News fields appear in prompt when provided."""
        from app.data_feeds.context import build_market_context
        from app.data_feeds.news_feed import NewsFeedResult

        ctx = build_market_context(
            news=NewsFeedResult(
                summary="FED signals rate cut",
                sentiment="positive",
                key_events=["FED dovish pivot", "ETH +5%"],
            ),
        )
        prompt = ctx.to_prompt_context()
        assert "[News]" in prompt
        assert "FED" in prompt
        assert "positive" in prompt
        assert "[Key Events]" in prompt

    def test_prompt_context_minimal(self):
        """Minimal context only contains geo-risk line."""
        from app.data_feeds.context import build_market_context

        ctx = build_market_context()
        prompt = ctx.to_prompt_context()
        assert "[Geopolitical Risk]" in prompt
        assert "[Aave Market]" not in prompt


class TestMarketContextInJudgment:
    """Test that MarketContext integrates with AI judgment pipeline."""

    def test_prompt_includes_market_context(self):
        """Verify market context text contains all provided fields."""
        from app.data_feeds.context import build_market_context

        ctx = build_market_context(
            aave_utilization_rate=Decimal("87.5"),
            aave_supply_apy=Decimal("3.2"),
            health_factor=Decimal("1.72"),
        )
        prompt_text = ctx.to_prompt_context()
        assert "Geopolitical Risk" in prompt_text
        assert "87.5" in prompt_text
        assert "1.72" in prompt_text

    def test_prompt_without_optional_fields(self):
        """Verify prompt works without optional fields (backward compat)."""
        from app.data_feeds.context import build_market_context

        ctx = build_market_context()
        prompt_text = ctx.to_prompt_context()
        assert "Geopolitical Risk" in prompt_text
        assert "Utilization" not in prompt_text

    def test_high_geo_risk_appears_in_prompt(self):
        """High geo risk score and summary appear in prompt text."""
        from app.data_feeds.context import build_market_context
        from app.data_feeds.geopolitical import GeoRiskResult

        high_risk = GeoRiskResult(
            geo_risk_score=85,
            summary="Major military conflict detected in Middle East",
        )
        ctx = build_market_context(geo_risk=high_risk)
        prompt_text = ctx.to_prompt_context()
        assert "85/100" in prompt_text
        assert "Middle East" in prompt_text

    def test_build_rag_prompt_with_market_context(self):
        """_build_rag_prompt appends market context section when provided."""
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService
        from app.data_feeds.context import build_market_context

        service = AIService()
        rag = RAGContext(chunks=["chunk1"], query="test")
        ctx = build_market_context(health_factor=Decimal("1.5"))
        _system, user = service._build_rag_prompt("test query", rag, market_context=ctx)
        assert "## Market Context (Real-time Data):" in user
        assert "1.5" in user

    def test_build_rag_prompt_without_market_context(self):
        """_build_rag_prompt works unchanged when market_context is None."""
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService

        service = AIService()
        rag = RAGContext(chunks=["chunk1"], query="test")
        _system, user = service._build_rag_prompt("test query", rag)
        assert "## Market Context" not in user
        assert "chunk1" in user


class TestGDELTFallback:
    @pytest.mark.asyncio
    async def test_gdelt_fallback_on_error(self) -> None:
        """パースエラー時にデフォルトGDELTEventを返すこと。"""
        from app.data_feeds.geopolitical import fetch_gdelt_events

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Expecting value")  # JSON parse error

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_gdelt_events(mock_client)

        assert result.avg_tone == Decimal("0")
        assert result.event_count == 0

    @pytest.mark.asyncio
    async def test_gdelt_fallback_on_http_error(self) -> None:
        """HTTP エラー時にデフォルトGDELTEventを返すこと。"""
        import httpx  # noqa: PLC0415

        from app.data_feeds.geopolitical import fetch_gdelt_events  # noqa: PLC0415

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_response
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_gdelt_events(mock_client)

        assert result.event_count == 0

    @pytest.mark.asyncio
    async def test_gdelt_429_triggers_retry_then_succeeds(self) -> None:
        """429受信後にリトライし、成功レスポンスを返すこと。"""
        from unittest.mock import patch  # noqa: PLC0415

        from app.data_feeds.geopolitical import fetch_gdelt_events  # noqa: PLC0415

        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status = MagicMock()
        success_response.json.return_value = [
            {"value": -5.0},
            {"value": -3.0},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[rate_limit_response, success_response])

        with patch("app.data_feeds.geopolitical.asyncio.sleep", new=AsyncMock()):
            result = await fetch_gdelt_events(mock_client)

        assert mock_client.get.call_count == 2
        assert result.event_count == 2
        assert result.avg_tone == Decimal("-4.0")

    @pytest.mark.asyncio
    async def test_gdelt_429_max_retries_returns_empty(self) -> None:
        """最大リトライ回数（3回）すべて429の場合、空のGDELTEventを返すこと。"""
        from unittest.mock import patch  # noqa: PLC0415

        from app.data_feeds.geopolitical import (  # noqa: PLC0415
            _GDELT_MAX_RETRIES,
            fetch_gdelt_events,
        )

        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=rate_limit_response)

        with patch("app.data_feeds.geopolitical.asyncio.sleep", new=AsyncMock()):
            result = await fetch_gdelt_events(mock_client)

        assert mock_client.get.call_count == _GDELT_MAX_RETRIES
        assert result.avg_tone == Decimal("0")
        assert result.event_count == 0

    def test_ai_judgment_continues_without_news_context(self) -> None:
        """ニュース/GDELT両方失敗でもAI判定が完走すること。"""
        from app.data_feeds.context import build_market_context
        from app.data_feeds.geopolitical import GeoRiskResult
        from app.data_feeds.news_feed import NewsFeedResult

        # Both feeds return fallback/default values
        fallback_news = NewsFeedResult(
            summary="ニュースデータ取得不可。市場データとAaveオンチェーンデータのみで判定。"
        )
        fallback_geo = GeoRiskResult(summary="No data available.")

        ctx = build_market_context(news=fallback_news, geo_risk=fallback_geo)
        prompt = ctx.to_prompt_context()

        # Judgment context is built successfully even with fallback data
        assert "ニュースデータ取得不可" in prompt
        assert "Geopolitical Risk" in prompt
