# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Finance Feed — Perplexity Finance (Sonar Pro)
Provides macro-economic and financial data context for AI judgment.

Data sources via Perplexity Finance:
  - SEC filings, FactSet, S&P Global
  - Coinbase, LSEG, Polymarket
  - FED/CPI calendar, macro indicators

Architecture:
  - Background task updates cache every 60 minutes
  - AI judgment reads from cache (0.01s)
  - Uses Sonar Pro model (higher reasoning, more sources)
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

_VALID_FED_STANCES = ("hawkish", "neutral", "dovish")
_VALID_STABLECOIN_RISKS = ("low", "medium", "high")

# 2026-05-28: staging soak で sonar-pro が 200/400 交互。
# 1) 非2xx 時に response body をログ (DoD: 真因特定)。
# 2) 4xx/5xx/timeout を一過性とみなし最大 1 回 retry (DoD: 200 安定化)。
_PERPLEXITY_MAX_ATTEMPTS = 2
_PERPLEXITY_RETRY_BACKOFF_SECONDS = 2.0
# auth 系は retry 不要 (key が違うだけ無駄打ち) なので除外。
_PERPLEXITY_NON_RETRIABLE_STATUSES = frozenset({401, 403})


# ============================================================
# Schemas
# ============================================================
class FinanceFeedResult(BaseModel):
    """Parsed macro/finance data for AI context."""

    macro_summary: str = Field(
        default="No finance data available yet.",
        description="Summary of macro-economic conditions",
    )
    fed_stance: str = Field(
        default="unknown",
        description="hawkish / neutral / dovish / unknown",
    )
    stablecoin_risk: str = Field(
        default="low",
        description="low / medium / high",
    )
    key_indicators: list[str] = Field(
        default_factory=list,
        description="Top 3-5 macro indicators",
    )
    sources_count: int = Field(default=0)
    updated_at: Optional[datetime] = None


# ============================================================
# Cache
# ============================================================
_finance_cache: Optional[FinanceFeedResult] = None
_finance_lock = asyncio.Lock()


def get_cached_finance() -> FinanceFeedResult:
    """Get cached finance data. Returns default if no cache."""
    if _finance_cache is not None:
        return _finance_cache
    return FinanceFeedResult()


# ============================================================
# Perplexity Finance Client
# ============================================================
async def fetch_finance_data(client: httpx.AsyncClient) -> FinanceFeedResult:
    """Fetch macro-economic data via Perplexity Sonar Pro API."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY not set. Skipping finance feed.")
        return FinanceFeedResult(macro_summary="API key not configured.")

    try:
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a macro-economic analyst specializing in crypto-relevant financial data. "
                        "Analyze the current macro environment and its impact on DeFi yields and stablecoin stability. "
                        "Focus on: FED interest rate policy, CPI/inflation data, USD strength, "
                        "stablecoin reserve health (USDC/USDT), institutional crypto flows, "
                        "and any SEC/regulatory developments affecting DeFi. "
                        "Format your response as JSON with keys: "
                        '"macro_summary" (2-3 sentences on overall macro conditions), '
                        '"fed_stance" ("hawkish", "neutral", or "dovish"), '
                        '"stablecoin_risk" ("low", "medium", or "high"), '
                        '"key_indicators" (list of 3-5 key data points with values).'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "What is the current macro-economic environment relevant to DeFi and stablecoin yields? "
                        "Include FED policy direction, latest CPI data, stablecoin reserve status, "
                        "and any institutional developments affecting Aave or DeFi lending markets."
                    ),
                },
            ],
            "max_tokens": 600,
            "temperature": 0.1,
        }

        resp = await _post_with_retry(client, payload, api_key)
        resp.raise_for_status()
        data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

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

            fed_stance = parsed.get("fed_stance", "unknown")
            if fed_stance not in _VALID_FED_STANCES:
                fed_stance = "unknown"

            stablecoin_risk = parsed.get("stablecoin_risk", "low")
            if stablecoin_risk not in _VALID_STABLECOIN_RISKS:
                stablecoin_risk = "low"

            # key_indicators may be list[str] or list[dict] depending on Perplexity API version.
            # Coerce dicts to "name: value" strings to avoid pydantic ValidationError.
            raw_indicators: list[object] = parsed.get("key_indicators", [])[:5]
            key_indicators: list[str] = [
                (
                    ": ".join(filter(None, [str(item.get("name", "")), str(item.get("value", ""))]))
                    if isinstance(item, dict)
                    else str(item)
                )
                for item in raw_indicators
            ]

            return FinanceFeedResult(
                macro_summary=str(parsed.get("macro_summary", content[:400])),
                fed_stance=fed_stance,
                stablecoin_risk=stablecoin_risk,
                key_indicators=key_indicators,
                sources_count=len(citations),
                updated_at=datetime.now(timezone.utc),
            )
        except (json.JSONDecodeError, KeyError):
            return FinanceFeedResult(
                macro_summary=content[:500],
                sources_count=len(citations),
                updated_at=datetime.now(timezone.utc),
            )

    except httpx.HTTPStatusError as exc:
        body_preview = ""
        try:
            body_preview = exc.response.text[:500]
        except Exception:  # noqa: BLE001 — body may be unreadable
            body_preview = "<body unavailable>"
        logger.error(
            "Perplexity Finance API error %s — body: %s",
            exc.response.status_code,
            body_preview,
        )
        return FinanceFeedResult(macro_summary="API error: %d" % exc.response.status_code)
    except Exception as exc:
        logger.error("Perplexity Finance fetch failed: %s", exc)
        return FinanceFeedResult(macro_summary="Finance data fetch failed.")


async def _post_with_retry(
    client: httpx.AsyncClient,
    payload: dict,
    api_key: str,
) -> httpx.Response:
    """POST to Perplexity with bounded retry on transient errors.

    Why: 2026-05-28 soak で sonar-pro が 200/400 交互。alternating pattern は
    Perplexity 内部の web search 層がたまに失敗する一過性エラーが本命なので、
    短い backoff の 1 回 retry で 200 化を狙う (Asana 1215189378837169)。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_resp: Optional[httpx.Response] = None
    for attempt in range(1, _PERPLEXITY_MAX_ATTEMPTS + 1):
        try:
            resp = await client.post(
                PERPLEXITY_API_URL,
                json=payload,
                headers=headers,
                timeout=20.0,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt >= _PERPLEXITY_MAX_ATTEMPTS:
                raise
            logger.warning(
                "Perplexity Finance transport error on attempt %d/%d: %s — retrying in %.1fs",
                attempt,
                _PERPLEXITY_MAX_ATTEMPTS,
                exc,
                _PERPLEXITY_RETRY_BACKOFF_SECONDS,
            )
            await asyncio.sleep(_PERPLEXITY_RETRY_BACKOFF_SECONDS)
            continue

        if resp.status_code < 400 or resp.status_code in _PERPLEXITY_NON_RETRIABLE_STATUSES:
            return resp

        last_resp = resp
        if attempt >= _PERPLEXITY_MAX_ATTEMPTS:
            return resp

        body_preview = ""
        try:
            body_preview = resp.text[:500]
        except Exception:  # noqa: BLE001
            body_preview = "<body unavailable>"
        logger.warning(
            "Perplexity Finance %s on attempt %d/%d — body: %s — retrying in %.1fs",
            resp.status_code,
            attempt,
            _PERPLEXITY_MAX_ATTEMPTS,
            body_preview,
            _PERPLEXITY_RETRY_BACKOFF_SECONDS,
        )
        await asyncio.sleep(_PERPLEXITY_RETRY_BACKOFF_SECONDS)

    # Unreachable: loop always returns or raises, but mypy/pyright wants this.
    assert last_resp is not None
    return last_resp


# ============================================================
# Background Update Task
# ============================================================
async def update_finance_cache() -> FinanceFeedResult:
    """Fetch fresh finance data and update the cache."""
    global _finance_cache
    async with httpx.AsyncClient() as client:
        result = await fetch_finance_data(client)

    # last-known-good: only update if we got real data or have no cache yet
    if result.updated_at is not None or _finance_cache is None:
        async with _finance_lock:
            _finance_cache = result
    else:
        logger.warning("Finance: API failed. Keeping last-known-good cache.")

    logger.info(
        "Finance updated: fed=%s, stablecoin_risk=%s, indicators=%d",
        result.fed_stance,
        result.stablecoin_risk,
        len(result.key_indicators),
    )
    return result


async def start_finance_background_task(interval_minutes: int = 60) -> None:
    """Background loop that updates finance cache periodically."""
    logger.info("Starting Finance feed background task (every %dmin)", interval_minutes)
    while True:
        try:
            await update_finance_cache()
        except Exception as exc:
            logger.error("Finance background update failed: %s", exc)
        await asyncio.sleep(interval_minutes * 60)
