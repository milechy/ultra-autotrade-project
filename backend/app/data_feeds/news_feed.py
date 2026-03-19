"""
News Feed — Perplexity Search API
Provides real-time crypto/DeFi news context for AI judgment.

Architecture:
  - Background task updates cache every 15 minutes
  - AI judgment reads from cache (0.01s)
  - Uses Sonar model (cheapest, search-optimized)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


# ============================================================
# Schemas
# ============================================================
class NewsFeedResult(BaseModel):
    """Parsed news feed data for AI context."""

    summary: str = Field(
        default="No news data available yet.",
        description="Summarized news context",
    )
    sentiment: str = Field(
        default="neutral",
        description="positive / neutral / negative",
    )
    key_events: list[str] = Field(
        default_factory=list,
        description="Top 3-5 key events",
    )
    sources_count: int = Field(default=0, description="Number of sources referenced")
    updated_at: Optional[datetime] = None


# ============================================================
# Cache
# ============================================================
_news_cache: Optional[NewsFeedResult] = None
_news_lock = asyncio.Lock()


def get_cached_news() -> NewsFeedResult:
    """Get cached news data. Returns default if no cache."""
    if _news_cache is not None:
        return _news_cache
    return NewsFeedResult()


# ============================================================
# Perplexity Search Client
# ============================================================
async def fetch_crypto_news(client: httpx.AsyncClient) -> NewsFeedResult:
    """Fetch latest crypto/DeFi news via Perplexity Sonar API."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY not set. Skipping news feed.")
        return NewsFeedResult(summary="API key not configured.")

    try:
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a crypto market analyst. Provide a concise summary of the latest "
                        "crypto and DeFi news that could affect Aave, stablecoin yields, or ETH price. "
                        "Focus on: regulatory changes, protocol updates, major market movements, "
                        "institutional activity, and macro events (FED, CPI). "
                        "Format your response as JSON with keys: "
                        '"summary" (2-3 sentences), '
                        '"sentiment" ("positive", "neutral", or "negative"), '
                        '"key_events" (list of 3-5 short event descriptions).'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "What are the latest developments in crypto, DeFi, and Aave "
                        "in the last 24 hours?"
                    ),
                },
            ],
            "max_tokens": 500,
            "temperature": 0.1,
        }

        resp = await client.post(
            PERPLEXITY_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        # Try to parse JSON from LLM response (strip markdown fences if present)
        try:
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()

            parsed = json.loads(clean)
            return NewsFeedResult(
                summary=parsed.get("summary", content[:300]),
                sentiment=parsed.get("sentiment", "neutral"),
                key_events=parsed.get("key_events", [])[:5],
                sources_count=len(citations),
                updated_at=datetime.now(timezone.utc),
            )
        except (json.JSONDecodeError, KeyError):
            return NewsFeedResult(
                summary=content[:500],
                sentiment="neutral",
                key_events=[],
                sources_count=len(citations),
                updated_at=datetime.now(timezone.utc),
            )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Perplexity API error: %s - %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        return NewsFeedResult(summary="API error: %d" % exc.response.status_code)
    except Exception as exc:
        logger.error("Perplexity fetch failed: %s", exc)
        return NewsFeedResult(summary="News fetch failed.")


# ============================================================
# Background Update Task
# ============================================================
async def update_news_cache() -> NewsFeedResult:
    """Fetch fresh news and update the cache."""
    global _news_cache
    async with httpx.AsyncClient() as client:
        result = await fetch_crypto_news(client)

    # last-known-good: only update if we got real data or have no cache yet
    if result.updated_at is not None or _news_cache is None:
        async with _news_lock:
            _news_cache = result
    else:
        logger.warning("News: API failed. Keeping last-known-good cache.")

    logger.info(
        "News updated: sentiment=%s, events=%d, sources=%d",
        result.sentiment,
        len(result.key_events),
        result.sources_count,
    )
    return result


async def start_news_background_task(interval_minutes: int = 15) -> None:
    """Background loop that updates news cache periodically."""
    logger.info("Starting News feed background task (every %dmin)", interval_minutes)
    while True:
        try:
            await update_news_cache()
        except Exception as exc:
            logger.error("News background update failed: %s", exc)
        await asyncio.sleep(interval_minutes * 60)
