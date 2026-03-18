"""Tests for geopolitical risk feed module."""

from decimal import Decimal

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

        ctx = build_market_context(
            news_summary="FED signals rate cut",
            news_sentiment="positive",
        )
        prompt = ctx.to_prompt_context()
        assert "[News]" in prompt
        assert "FED" in prompt
        assert "positive" in prompt

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
        prompt = service._build_rag_prompt("test query", rag, market_context=ctx)
        assert "## Market Context (Real-time Data):" in prompt
        assert "1.5" in prompt

    def test_build_rag_prompt_without_market_context(self):
        """_build_rag_prompt works unchanged when market_context is None."""
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService

        service = AIService()
        rag = RAGContext(chunks=["chunk1"], query="test")
        prompt = service._build_rag_prompt("test query", rag)
        assert "## Market Context" not in prompt
        assert "chunk1" in prompt
