"""
Market Context — Aggregated data for AI judgment.
Combines all data feed caches into a single context object.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.data_feeds.finance_feed import FinanceFeedResult, get_cached_finance
from app.data_feeds.geopolitical import GeoRiskResult, get_cached_geo_risk
from app.data_feeds.news_feed import NewsFeedResult, get_cached_news


class MarketContext(BaseModel):
    """Aggregated market context for AI judgment.

    All data is pre-cached; reading this takes ~0.01s.
    """

    # Geopolitical risk (GDELT + USGS)
    geo_risk: GeoRiskResult = Field(default_factory=get_cached_geo_risk)

    # Aave market data (populated from Aave client)
    aave_utilization_rate: Optional[Decimal] = None
    aave_supply_apy: Optional[Decimal] = None
    aave_borrow_apy: Optional[Decimal] = None
    health_factor: Optional[Decimal] = None

    # News context (Perplexity Sonar — 15min cache)
    news: NewsFeedResult = Field(default_factory=get_cached_news)

    # Macro context (Perplexity Finance Sonar Pro — 60min cache)
    finance: FinanceFeedResult = Field(default_factory=get_cached_finance)

    # Social sentiment (Phase 2 optional — Santiment)
    social_sentiment_score: Optional[Decimal] = None

    # Metadata
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_prompt_context(self) -> str:
        """Format as text block for LLM prompt injection."""
        parts = []

        parts.append(
            f"[Geopolitical Risk] Score: {self.geo_risk.geo_risk_score}/100"
            f" — {self.geo_risk.summary}"
        )

        if self.aave_utilization_rate is not None:
            parts.append(
                f"[Aave Market] Utilization: {self.aave_utilization_rate}%,"
                f" Supply APY: {self.aave_supply_apy}%,"
                f" Borrow APY: {self.aave_borrow_apy}%"
            )

        if self.health_factor is not None:
            parts.append(f"[Health Factor] {self.health_factor}")

        if self.news.summary and "No news" not in self.news.summary:
            parts.append(f"[News] {self.news.summary} (Sentiment: {self.news.sentiment})")
            if self.news.key_events:
                parts.append("[Key Events] " + " | ".join(self.news.key_events))

        if "No finance data" not in self.finance.macro_summary:
            parts.append(
                f"[Macro] {self.finance.macro_summary}"
                f" (FED: {self.finance.fed_stance},"
                f" Stablecoin risk: {self.finance.stablecoin_risk})"
            )
            if self.finance.key_indicators:
                parts.append("[Macro Indicators] " + " | ".join(self.finance.key_indicators))

        if self.social_sentiment_score is not None:
            parts.append(f"[Social Sentiment] {self.social_sentiment_score}/100")

        return "\n".join(parts)


def build_market_context(**overrides: object) -> MarketContext:
    """Build a MarketContext from cached data feeds plus optional overrides.

    Usage in AI service:
        ctx = build_market_context(
            aave_utilization_rate=Decimal("87.5"),
            health_factor=Decimal("1.72"),
        )
        prompt_text = ctx.to_prompt_context()
    """
    return MarketContext(**overrides)
