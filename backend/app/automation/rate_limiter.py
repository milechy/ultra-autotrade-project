# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/rate_limiter.py
"""
APIレート制限トラッカー（インメモリ、スライディングウィンドウ）。

対象API:
- Claude API (calls/min, tokens/day)
- OpenAI API (calls/min, tokens/day)
- X API (calls/15min)
- ccxt Exchange API (calls/min)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING, Deque, Optional

if TYPE_CHECKING:
    from app.automation.rate_limiter_schemas import RateLimitStatus


@dataclass
class WindowCounter:
    """スライディングウィンドウカウンター（スレッドセーフ）。"""

    window_seconds: int
    limit: int
    _timestamps: Deque[float] = field(default_factory=deque)
    _lock: Lock = field(default_factory=Lock)

    def record(self) -> None:
        """1コールを記録する。"""
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)
            self._prune(now)

    def record_tokens(self, count: int) -> None:
        """複数トークンを記録する（countの回数分push）。"""
        now = time.monotonic()
        with self._lock:
            for _ in range(count):
                self._timestamps.append(now)
            self._prune(now)

    def current_count(self) -> int:
        """現在ウィンドウ内のカウント数を返す。"""
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            return len(self._timestamps)

    def reset_in_seconds(self) -> float:
        """最も古いエントリーがウィンドウから外れるまでの秒数を返す。"""
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if not self._timestamps:
                return 0.0
            oldest = self._timestamps[0]
            remaining = (oldest + self.window_seconds) - now
            return max(0.0, remaining)

    def usage_pct(self) -> float:
        """使用率（0.0〜100.0）を返す。"""
        if self.limit <= 0:
            return 0.0
        return min(100.0, self.current_count() / self.limit * 100.0)

    def _prune(self, now: float) -> None:
        """ウィンドウ外の古いエントリーを削除（ロック保持状態で呼ぶこと）。"""
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def reset(self) -> None:
        """テスト用リセット。"""
        with self._lock:
            self._timestamps.clear()


class RateLimiterService:
    """
    全APIのレート制限カウンターを管理するサービス。

    各APIの制限値:
    - Claude: 50 calls/min, 1_000_000 tokens/day
    - OpenAI: 60 calls/min, 500_000 tokens/day
    - X API: 180 calls/15min
    - Exchange: 120 calls/min
    """

    # Limits
    CLAUDE_CALLS_PER_MIN = 50
    CLAUDE_TOKENS_PER_DAY = 1_000_000
    OPENAI_CALLS_PER_MIN = 60
    OPENAI_TOKENS_PER_DAY = 500_000
    X_CALLS_PER_15MIN = 180
    EXCHANGE_CALLS_PER_MIN = 120

    def __init__(self) -> None:
        self.claude_calls = WindowCounter(window_seconds=60, limit=self.CLAUDE_CALLS_PER_MIN)
        self.claude_tokens = WindowCounter(window_seconds=86400, limit=self.CLAUDE_TOKENS_PER_DAY)
        self.openai_calls = WindowCounter(window_seconds=60, limit=self.OPENAI_CALLS_PER_MIN)
        self.openai_tokens = WindowCounter(window_seconds=86400, limit=self.OPENAI_TOKENS_PER_DAY)
        self.x_calls = WindowCounter(window_seconds=900, limit=self.X_CALLS_PER_15MIN)
        self.exchange_calls = WindowCounter(window_seconds=60, limit=self.EXCHANGE_CALLS_PER_MIN)

    def record_claude_call(self, tokens: Optional[int] = None) -> None:
        self.claude_calls.record()
        if tokens and tokens > 0:
            self.claude_tokens.record_tokens(tokens)

    def record_openai_call(self, tokens: Optional[int] = None) -> None:
        self.openai_calls.record()
        if tokens and tokens > 0:
            self.openai_tokens.record_tokens(tokens)

    def record_x_call(self) -> None:
        self.x_calls.record()

    def record_exchange_call(self) -> None:
        self.exchange_calls.record()

    def get_status(self) -> "RateLimitStatus":
        from app.automation.rate_limiter_schemas import (
            ApiRateLimitEntry,
            RateLimitStatus,
        )

        now = datetime.now(timezone.utc)

        return RateLimitStatus(
            generated_at=now,
            apis=[
                ApiRateLimitEntry(
                    api_name="claude_calls",
                    display_name="Claude API (calls/min)",
                    current=self.claude_calls.current_count(),
                    limit=self.CLAUDE_CALLS_PER_MIN,
                    window_seconds=60,
                    usage_pct=round(self.claude_calls.usage_pct(), 1),
                    reset_in_seconds=round(self.claude_calls.reset_in_seconds(), 1),
                ),
                ApiRateLimitEntry(
                    api_name="claude_tokens",
                    display_name="Claude API (tokens/day)",
                    current=self.claude_tokens.current_count(),
                    limit=self.CLAUDE_TOKENS_PER_DAY,
                    window_seconds=86400,
                    usage_pct=round(self.claude_tokens.usage_pct(), 1),
                    reset_in_seconds=round(self.claude_tokens.reset_in_seconds(), 1),
                ),
                ApiRateLimitEntry(
                    api_name="openai_calls",
                    display_name="OpenAI API (calls/min)",
                    current=self.openai_calls.current_count(),
                    limit=self.OPENAI_CALLS_PER_MIN,
                    window_seconds=60,
                    usage_pct=round(self.openai_calls.usage_pct(), 1),
                    reset_in_seconds=round(self.openai_calls.reset_in_seconds(), 1),
                ),
                ApiRateLimitEntry(
                    api_name="openai_tokens",
                    display_name="OpenAI API (tokens/day)",
                    current=self.openai_tokens.current_count(),
                    limit=self.OPENAI_TOKENS_PER_DAY,
                    window_seconds=86400,
                    usage_pct=round(self.openai_tokens.usage_pct(), 1),
                    reset_in_seconds=round(self.openai_tokens.reset_in_seconds(), 1),
                ),
                ApiRateLimitEntry(
                    api_name="x_calls",
                    display_name="X API (calls/15min)",
                    current=self.x_calls.current_count(),
                    limit=self.X_CALLS_PER_15MIN,
                    window_seconds=900,
                    usage_pct=round(self.x_calls.usage_pct(), 1),
                    reset_in_seconds=round(self.x_calls.reset_in_seconds(), 1),
                ),
                ApiRateLimitEntry(
                    api_name="exchange_calls",
                    display_name="Exchange API (calls/min)",
                    current=self.exchange_calls.current_count(),
                    limit=self.EXCHANGE_CALLS_PER_MIN,
                    window_seconds=60,
                    usage_pct=round(self.exchange_calls.usage_pct(), 1),
                    reset_in_seconds=round(self.exchange_calls.reset_in_seconds(), 1),
                ),
            ],
        )


# Singleton
_rate_limiter: Optional[RateLimiterService] = None


def get_rate_limiter() -> RateLimiterService:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiterService()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """テスト用リセット。"""
    global _rate_limiter
    _rate_limiter = None
