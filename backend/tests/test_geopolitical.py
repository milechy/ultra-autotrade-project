"""Tests for geopolitical risk feed module."""
from decimal import Decimal

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
        assert any(
            word in result.summary.lower()
            for word in ("conflict", "events", "tension")
        )

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
