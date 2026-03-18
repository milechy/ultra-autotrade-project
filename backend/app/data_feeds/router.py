"""API endpoints for external data feeds."""

from fastapi import APIRouter

from app.automation.howl_review import HOWLReport, run_howl_review
from app.data_feeds.finance_feed import FinanceFeedResult, get_cached_finance, update_finance_cache
from app.data_feeds.geopolitical import GeoRiskResult, get_cached_geo_risk, update_geo_risk_cache
from app.data_feeds.news_feed import NewsFeedResult, get_cached_news, update_news_cache

router = APIRouter(prefix="/api/data-feeds", tags=["data-feeds"])


@router.get("/geo-risk")
async def get_geo_risk() -> GeoRiskResult:
    """Get current geopolitical risk score (from cache)."""
    return get_cached_geo_risk()


@router.post("/geo-risk/refresh")
async def refresh_geo_risk() -> GeoRiskResult:
    """Force refresh geopolitical risk data (admin only)."""
    return await update_geo_risk_cache()


@router.get("/news")
async def get_news() -> NewsFeedResult:
    """Get latest crypto/DeFi news summary (from cache)."""
    return get_cached_news()


@router.post("/news/refresh")
async def refresh_news() -> NewsFeedResult:
    """Force refresh news data (admin only)."""
    return await update_news_cache()


@router.get("/finance")
async def get_finance() -> FinanceFeedResult:
    """Get current macro-economic finance data (from cache)."""
    return get_cached_finance()


@router.post("/finance/refresh")
async def refresh_finance() -> FinanceFeedResult:
    """Force refresh finance data (admin only)."""
    return await update_finance_cache()


@router.post("/howl/review")
async def trigger_howl_review() -> HOWLReport:
    """Trigger HOWL self-improvement review (admin only)."""
    return await run_howl_review()
