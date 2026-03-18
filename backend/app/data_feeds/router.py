"""API endpoints for external data feeds."""
from fastapi import APIRouter

from app.data_feeds.geopolitical import get_cached_geo_risk, update_geo_risk_cache

router = APIRouter(prefix="/api/data-feeds", tags=["data-feeds"])


@router.get("/geo-risk")
async def get_geo_risk():
    """Get current geopolitical risk score (from cache)."""
    return get_cached_geo_risk()


@router.post("/geo-risk/refresh")
async def refresh_geo_risk():
    """Force refresh geopolitical risk data (admin only)."""
    return await update_geo_risk_cache()
