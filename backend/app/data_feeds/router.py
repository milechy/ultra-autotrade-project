"""API endpoints for external data feeds."""

from decimal import Decimal

from fastapi import APIRouter

from app.ai.agents import run_all_agents
from app.automation.howl_review import HOWLReport, run_howl_review
from app.data_feeds.context import build_market_context
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


@router.get("/agents")
async def get_agent_signals() -> dict:
    """Run all multi-agent signals with current market context."""
    context = build_market_context()
    mac = run_all_agents(context)
    return {
        "consensus": mac.consensus_bias().value,
        "average_confidence": mac.average_confidence(),
        "agents": {
            "indicator": mac.indicator_signal.model_dump() if mac.indicator_signal else None,
            "pattern": mac.pattern_signal.model_dump() if mac.pattern_signal else None,
            "risk": mac.risk_signal.model_dump() if mac.risk_signal else None,
            "macro": mac.macro_signal.model_dump() if mac.macro_signal else None,
        },
        "decision_prompt_preview": mac.to_decision_prompt()[:500],
    }


@router.post("/agents/simulate")
async def simulate_agent_signals(
    health_factor: float = 1.72,
    utilization_rate: float = 78.5,
    supply_apy: float = 3.2,
) -> dict:
    """Run all multi-agent signals with simulated market context."""
    context = build_market_context(
        health_factor=Decimal(str(health_factor)),
        aave_utilization_rate=Decimal(str(utilization_rate)),
        aave_supply_apy=Decimal(str(supply_apy)),
    )
    mac = run_all_agents(context)
    return {
        "consensus": mac.consensus_bias().value,
        "average_confidence": mac.average_confidence(),
        "agents": {
            "indicator": mac.indicator_signal.model_dump() if mac.indicator_signal else None,
            "pattern": mac.pattern_signal.model_dump() if mac.pattern_signal else None,
            "risk": mac.risk_signal.model_dump() if mac.risk_signal else None,
            "macro": mac.macro_signal.model_dump() if mac.macro_signal else None,
        },
        "decision_prompt_preview": mac.to_decision_prompt()[:800],
    }
