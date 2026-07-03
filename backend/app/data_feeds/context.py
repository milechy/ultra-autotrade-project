# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Market Context — Aggregated data for AI judgment.
Combines all data feed caches into a single context object.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.ai.judgment_log import CognitiveState
from app.data_feeds.finance_feed import FinanceFeedResult, get_cached_finance
from app.data_feeds.geopolitical import GeoRiskResult, get_cached_geo_risk
from app.data_feeds.mmt_feed import MMTData, get_cached_mmt_data
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

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """借入なし (HF=∞) を 999.0 に変換して pydantic finite_number 制約を回避する。"""
        if v is not None and isinstance(v, Decimal) and not v.is_finite():
            return Decimal("999.0")
        return v

    # News context (Perplexity Sonar — 15min cache)
    news: NewsFeedResult = Field(default_factory=get_cached_news)

    # Macro context (Perplexity Finance Sonar Pro — 60min cache)
    finance: FinanceFeedResult = Field(default_factory=get_cached_finance)

    # MMT market data (mmt.gg — funding rate, OI, candles — 30min cache)
    mmt_data: Optional[MMTData] = Field(default_factory=get_cached_mmt_data)

    # Social sentiment (Phase 2 optional — Santiment)
    social_sentiment_score: Optional[Decimal] = None

    # AI cognitive state (recent judgment history for pattern detection)
    cognitive_state: Optional[CognitiveState] = None

    # GHO/USDC 借入通貨最適化ヒント（Phase 1: 観測のみ）。
    # "recommend_gho" | "recommend_usdc" | None（未取得/失敗時、fail-open）。
    # 利回り最適化の参考情報であり BUY/SELL/HOLD の方向性には一切関与しない
    # （borrow_currency_signal() は Aave/borrow_optimizer.py 参照）。
    # Phase 1 では to_prompt_context() に注入しない（raw_features 記録のみ）。
    # プロンプト注入は Phase 2（別PR、本番soak確認後）で追加する。
    gho_borrow_signal: Optional[str] = None

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

        if self.mmt_data is not None:
            mmt_section = self.mmt_data.to_prompt_section()
            if mmt_section:
                parts.append(mmt_section)

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
