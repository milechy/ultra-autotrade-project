# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/health/cache.py
"""In-memory cache for GET /health/detail with asyncio.Lock + 5min TTL.

A single populate() call refreshes safety/quota probe state via probes.py.
Background task in main.py refreshes every TTL; on-demand requests hit cache.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from app.health.schemas import HealthDetailResponse

logger = logging.getLogger(__name__)

_TTL = timedelta(minutes=5)


class HealthDetailCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: Optional[HealthDetailResponse] = None
        self._populated_at: Optional[datetime] = None

    async def get_or_populate(
        self,
        populator: Callable[[], Awaitable[HealthDetailResponse]],
    ) -> HealthDetailResponse:
        """Return cached value, repopulating on cold start or TTL expiry."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._data is not None and self._populated_at is not None:
                if now - self._populated_at < _TTL:
                    return self._data
            self._data = await populator()
            self._populated_at = now
            return self._data

    async def refresh(
        self,
        populator: Callable[[], Awaitable[HealthDetailResponse]],
    ) -> None:
        """Force refresh (used by background task)."""
        async with self._lock:
            try:
                self._data = await populator()
                self._populated_at = datetime.now(timezone.utc)
            except Exception as exc:
                logger.error("health detail cache refresh failed: %s", exc)

    def invalidate(self) -> None:
        self._data = None
        self._populated_at = None


_singleton: Optional[HealthDetailCache] = None


def get_health_detail_cache() -> HealthDetailCache:
    global _singleton
    if _singleton is None:
        _singleton = HealthDetailCache()
    return _singleton


def reset_health_detail_cache() -> None:
    """Test helper — drop the singleton instance."""
    global _singleton
    _singleton = None
