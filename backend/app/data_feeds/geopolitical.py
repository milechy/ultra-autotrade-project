"""
Geopolitical Risk Feed — GDELT + USGS
Provides geoRiskScore (0-100) for AI judgment context.

Data sources:
  - GDELT GKG API: Global event tone, conflict events
  - USGS Earthquake API: Significant seismic events

Architecture:
  - Background task updates cache every 30 minutes
  - AI judgment reads from cache (0.01s) not live API (2-3s)
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================
# Schemas
# ============================================================
class GDELTEvent(BaseModel):
    """Parsed GDELT event data."""

    avg_tone: Decimal = Field(default=Decimal("0"), description="Average tone (-100 to +100)")
    event_count: int = Field(default=0, description="Number of conflict events")
    goldstein_scale: Decimal = Field(
        default=Decimal("0"), description="Goldstein scale (-10 to +10)"
    )


class USGSEarthquake(BaseModel):
    """Significant earthquake data."""

    magnitude: Decimal = Field(default=Decimal("0"))
    location: str = ""
    timestamp: Optional[datetime] = None


class GeoRiskResult(BaseModel):
    """Combined geopolitical risk assessment."""

    geo_risk_score: int = Field(
        default=50, ge=0, le=100, description="0=safe, 100=extreme risk"
    )
    gdelt_tone: Decimal = Field(default=Decimal("0"))
    gdelt_event_count: int = Field(default=0)
    earthquake_count: int = Field(default=0)
    max_earthquake_magnitude: Decimal = Field(default=Decimal("0"))
    summary: str = ""
    updated_at: Optional[datetime] = None

    model_config = {"arbitrary_types_allowed": True}


# ============================================================
# Cache
# ============================================================
_cache: Optional[GeoRiskResult] = None
_cache_lock = asyncio.Lock()


def get_cached_geo_risk() -> GeoRiskResult:
    """Get cached geopolitical risk data. Returns default if no cache."""
    if _cache is not None:
        return _cache
    return GeoRiskResult(summary="No data available yet. Cache warming up.")


# ============================================================
# GDELT Client
# ============================================================
GDELT_GKG_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_gdelt_events(client: httpx.AsyncClient) -> GDELTEvent:
    """Fetch conflict/instability events from GDELT GKG API."""
    try:
        params = {
            "query": "conflict OR military OR sanctions OR crisis OR war",
            "mode": "tonechart",
            "timespan": "24h",
            "format": "json",
        }
        resp = await client.get(GDELT_GKG_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list) and len(data) > 0:
            tones = [float(item.get("value", 0)) for item in data if "value" in item]
            avg_tone = Decimal(str(sum(tones) / len(tones))) if tones else Decimal("0")
            event_count = len(data)
        else:
            avg_tone = Decimal("0")
            event_count = 0

        return GDELTEvent(avg_tone=avg_tone, event_count=event_count)
    except Exception as exc:
        logger.warning("GDELT fetch failed: %s", exc)
        return GDELTEvent()


# ============================================================
# USGS Earthquake Client
# ============================================================
USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


async def fetch_usgs_earthquakes(client: httpx.AsyncClient) -> list[USGSEarthquake]:
    """Fetch significant earthquakes from USGS (M5.0+ in last 24h)."""
    try:
        now = datetime.now(timezone.utc)
        params = {
            "format": "geojson",
            "starttime": (now - timedelta(hours=24)).strftime("%Y-%m-%d"),
            "endtime": now.strftime("%Y-%m-%d"),
            "minmagnitude": "5.0",
            "orderby": "magnitude",
        }
        resp = await client.get(USGS_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        earthquakes = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            earthquakes.append(
                USGSEarthquake(
                    magnitude=Decimal(str(props.get("mag", 0))),
                    location=props.get("place", "Unknown"),
                    timestamp=(
                        datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc)
                        if props.get("time")
                        else None
                    ),
                )
            )
        return earthquakes
    except Exception as exc:
        logger.warning("USGS fetch failed: %s", exc)
        return []


# ============================================================
# Risk Score Calculator
# ============================================================
def calculate_geo_risk_score(
    gdelt: GDELTEvent,
    earthquakes: list[USGSEarthquake],
) -> GeoRiskResult:
    """
    Calculate composite geopolitical risk score (0-100).

    Scoring:
      - GDELT tone: negative tone = higher risk (0-40 points)
      - GDELT event count: more conflict events = higher risk (0-30 points)
      - Earthquakes: large quakes near infrastructure = higher risk (0-30 points)
    """
    # GDELT tone score (0-40): tone -10 or worse = 40, +5 or better = 0
    tone_float = float(gdelt.avg_tone)
    if tone_float <= -10:
        tone_score = 40
    elif tone_float >= 5:
        tone_score = 0
    else:
        tone_score = int(40 * (5 - tone_float) / 15)

    # GDELT event count score (0-30): 500+ events = max
    event_score = min(30, int(gdelt.event_count / 500 * 30))

    # Earthquake score (0-30)
    max_mag = Decimal("0")
    for eq in earthquakes:
        if eq.magnitude > max_mag:
            max_mag = eq.magnitude

    if max_mag >= Decimal("7.0"):
        quake_score = 30
    elif max_mag >= Decimal("6.0"):
        quake_score = 20
    elif max_mag >= Decimal("5.5"):
        quake_score = 10
    elif max_mag >= Decimal("5.0"):
        quake_score = 5
    else:
        quake_score = 0

    total_score = min(100, tone_score + event_score + quake_score)

    parts = []
    if tone_score >= 25:
        parts.append("Global conflict tension is elevated")
    if event_score >= 15:
        parts.append(f"{gdelt.event_count} conflict events detected in 24h")
    if quake_score >= 10:
        loc = earthquakes[0].location if earthquakes else "unknown"
        parts.append(f"M{max_mag} earthquake detected: {loc}")
    if not parts:
        parts.append("Geopolitical environment is stable")

    return GeoRiskResult(
        geo_risk_score=total_score,
        gdelt_tone=gdelt.avg_tone,
        gdelt_event_count=gdelt.event_count,
        earthquake_count=len(earthquakes),
        max_earthquake_magnitude=max_mag,
        summary=". ".join(parts),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================
# Background Update Task
# ============================================================
async def update_geo_risk_cache() -> GeoRiskResult:
    """Fetch fresh data and update the cache. Called by background scheduler."""
    global _cache
    async with httpx.AsyncClient() as client:
        gdelt, earthquakes = await asyncio.gather(
            fetch_gdelt_events(client),
            fetch_usgs_earthquakes(client),
        )

    result = calculate_geo_risk_score(gdelt, earthquakes)

    async with _cache_lock:
        _cache = result

    logger.info(
        "GeoRisk updated: score=%d, tone=%s, events=%d, quakes=%d",
        result.geo_risk_score,
        result.gdelt_tone,
        result.gdelt_event_count,
        result.earthquake_count,
    )
    return result


async def start_geo_risk_background_task(interval_minutes: int = 30) -> None:
    """Background loop that updates geo risk cache periodically."""
    logger.info("Starting GeoRisk background task (every %dmin)", interval_minutes)
    while True:
        try:
            await update_geo_risk_cache()
        except Exception as exc:
            logger.error("GeoRisk background update failed: %s", exc)
        await asyncio.sleep(interval_minutes * 60)
