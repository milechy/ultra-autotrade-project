# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/health/probes.py
"""Background probes that populate health/detail component state.

Three independent loops update module-level state:
- openai_probe_loop:      every 5min, cost=0 (GET /v1/models)
- perplexity_probe_loop:  every 15min, cost ~$0.10/day (POST /chat/completions, max_tokens=1)
- aave_safety_probe_loop: every 5min, calls is_oracle_fresh / is_reserve_healthy
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.health.schemas import ApiQuotaStatus

logger = logging.getLogger(__name__)

OPENAI_PROBE_INTERVAL_SECONDS = 300  # 5 min
PERPLEXITY_PROBE_INTERVAL_SECONDS = 900  # 15 min
AAVE_SAFETY_PROBE_INTERVAL_SECONDS = 300  # 5 min

_HTTP_TIMEOUT_SECONDS = 10

# --- module-level cached state (read by populator) ---
_openai_status: ApiQuotaStatus = ApiQuotaStatus(reachable=False, last_check=None, last_error=None)
_perplexity_status: ApiQuotaStatus = ApiQuotaStatus(
    reachable=False, last_check=None, last_error=None
)
_oracle_fresh: bool = True  # optimistic default; flipped by probe loop
_reserve_healthy: bool = True


def get_openai_status() -> ApiQuotaStatus:
    return _openai_status


def get_perplexity_status() -> ApiQuotaStatus:
    return _perplexity_status


def get_oracle_fresh() -> bool:
    return _oracle_fresh


def get_reserve_healthy() -> bool:
    return _reserve_healthy


def reset_probe_state() -> None:
    """Test helper — reset all module-level state to defaults."""
    global _openai_status, _perplexity_status, _oracle_fresh, _reserve_healthy
    _openai_status = ApiQuotaStatus(reachable=False, last_check=None, last_error=None)
    _perplexity_status = ApiQuotaStatus(reachable=False, last_check=None, last_error=None)
    _oracle_fresh = True
    _reserve_healthy = True


def _classify_http_error(status_code: int) -> Optional[str]:
    if status_code in (401, 403):
        return "auth_failed"
    if status_code == 429:
        return "quota_exceeded"
    if status_code >= 500:
        return "unknown"
    return None


async def probe_openai_once() -> ApiQuotaStatus:
    """One-shot probe of OpenAI /v1/models (cost=0)."""
    global _openai_status
    api_key = os.getenv("OPENAI_API_KEY", "")
    now = datetime.now(timezone.utc)

    if not api_key:
        _openai_status = ApiQuotaStatus(reachable=False, last_check=now, last_error="auth_failed")
        return _openai_status

    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            _openai_status = ApiQuotaStatus(reachable=True, last_check=now, last_error=None)
        else:
            err = _classify_http_error(resp.status_code) or "unknown"
            _openai_status = ApiQuotaStatus(reachable=False, last_check=now, last_error=err)
    except (TimeoutError, asyncio.TimeoutError):
        _openai_status = ApiQuotaStatus(reachable=False, last_check=now, last_error="timeout")
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai probe failed: %s", exc)
        _openai_status = ApiQuotaStatus(reachable=False, last_check=now, last_error="unknown")

    return _openai_status


async def probe_perplexity_once() -> ApiQuotaStatus:
    """One-shot probe of Perplexity /chat/completions (~$0.001 per call)."""
    global _perplexity_status
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    now = datetime.now(timezone.utc)

    if not api_key:
        _perplexity_status = ApiQuotaStatus(
            reachable=False, last_check=now, last_error="auth_failed"
        )
        return _perplexity_status

    try:
        import httpx  # noqa: PLC0415

        payload = {
            "model": "sonar",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code == 200:
            _perplexity_status = ApiQuotaStatus(reachable=True, last_check=now, last_error=None)
        else:
            err = _classify_http_error(resp.status_code) or "unknown"
            _perplexity_status = ApiQuotaStatus(reachable=False, last_check=now, last_error=err)
    except (TimeoutError, asyncio.TimeoutError):
        _perplexity_status = ApiQuotaStatus(reachable=False, last_check=now, last_error="timeout")
    except Exception as exc:  # noqa: BLE001
        logger.warning("perplexity probe failed: %s", exc)
        _perplexity_status = ApiQuotaStatus(reachable=False, last_check=now, last_error="unknown")

    return _perplexity_status


async def probe_aave_safety_once() -> tuple[bool, bool]:
    """One-shot probe of oracle freshness and reserve health."""
    global _oracle_fresh, _reserve_healthy

    loop = asyncio.get_running_loop()
    try:
        from app.aave.oracle_checker import is_oracle_fresh  # noqa: PLC0415

        _oracle_fresh = await loop.run_in_executor(None, is_oracle_fresh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oracle probe failed (fail-closed): %s", exc)
        _oracle_fresh = False

    try:
        from app.aave.reserve_monitor import is_reserve_healthy  # noqa: PLC0415

        _reserve_healthy = await loop.run_in_executor(None, is_reserve_healthy)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reserve probe failed (fail-closed): %s", exc)
        _reserve_healthy = False

    return _oracle_fresh, _reserve_healthy


async def openai_probe_loop(
    interval_seconds: int = OPENAI_PROBE_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            await probe_openai_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("openai_probe_loop iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def perplexity_probe_loop(
    interval_seconds: int = PERPLEXITY_PROBE_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            await probe_perplexity_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("perplexity_probe_loop iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def aave_safety_probe_loop(
    interval_seconds: int = AAVE_SAFETY_PROBE_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            await probe_aave_safety_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("aave_safety_probe_loop iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)
