# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_automation_rate_limiter.py
"""レート制限カウンターのテスト。"""

import time

import pytest

from app.automation.rate_limiter import RateLimiterService, WindowCounter, reset_rate_limiter


class TestWindowCounter:
    def test_initial_count_zero(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        assert counter.current_count() == 0

    def test_record_increments(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        counter.record()
        counter.record()
        assert counter.current_count() == 2

    def test_usage_pct_zero_initially(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        assert counter.usage_pct() == 0.0

    def test_usage_pct_after_records(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        for _ in range(50):
            counter.record()
        assert counter.usage_pct() == 50.0

    def test_usage_pct_capped_at_100(self):
        counter = WindowCounter(window_seconds=60, limit=10)
        for _ in range(20):
            counter.record()
        assert counter.usage_pct() == 100.0

    def test_reset_clears_counter(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        counter.record()
        counter.record()
        counter.reset()
        assert counter.current_count() == 0

    def test_record_tokens(self):
        counter = WindowCounter(window_seconds=60, limit=1000)
        counter.record_tokens(100)
        assert counter.current_count() == 100

    def test_window_expiry(self):
        """1秒ウィンドウのカウンターは1秒後にリセットされる。"""
        counter = WindowCounter(window_seconds=1, limit=100)
        counter.record()
        assert counter.current_count() == 1
        time.sleep(1.1)
        assert counter.current_count() == 0

    def test_reset_in_seconds_zero_when_empty(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        assert counter.reset_in_seconds() == 0.0

    def test_reset_in_seconds_positive_after_record(self):
        counter = WindowCounter(window_seconds=60, limit=100)
        counter.record()
        assert counter.reset_in_seconds() > 0.0
        assert counter.reset_in_seconds() <= 60.0


class TestRateLimiterService:
    def setup_method(self):
        reset_rate_limiter()

    def teardown_method(self):
        reset_rate_limiter()

    def test_record_claude_call(self):
        service = RateLimiterService()
        service.record_claude_call()
        assert service.claude_calls.current_count() == 1

    def test_record_claude_call_with_tokens(self):
        service = RateLimiterService()
        service.record_claude_call(tokens=100)
        assert service.claude_calls.current_count() == 1
        assert service.claude_tokens.current_count() == 100

    def test_record_openai_call(self):
        service = RateLimiterService()
        service.record_openai_call()
        assert service.openai_calls.current_count() == 1

    def test_record_x_call(self):
        service = RateLimiterService()
        service.record_x_call()
        assert service.x_calls.current_count() == 1

    def test_record_exchange_call(self):
        service = RateLimiterService()
        service.record_exchange_call()
        assert service.exchange_calls.current_count() == 1

    def test_get_status_returns_all_apis(self):
        service = RateLimiterService()
        status = service.get_status()
        api_names = [a.api_name for a in status.apis]
        assert "claude_calls" in api_names
        assert "claude_tokens" in api_names
        assert "openai_calls" in api_names
        assert "openai_tokens" in api_names
        assert "x_calls" in api_names
        assert "exchange_calls" in api_names

    def test_get_status_usage_pct_zero_initially(self):
        service = RateLimiterService()
        status = service.get_status()
        for api in status.apis:
            assert api.usage_pct == 0.0

    def test_get_status_after_calls(self):
        service = RateLimiterService()
        for _ in range(10):
            service.record_claude_call()
        status = service.get_status()
        claude_entry = next(a for a in status.apis if a.api_name == "claude_calls")
        assert claude_entry.current == 10
        assert claude_entry.usage_pct == pytest.approx(10 / 50 * 100, rel=0.01)

    def test_get_status_generated_at_is_utc(self):
        service = RateLimiterService()
        status = service.get_status()
        assert status.generated_at.tzinfo is not None

    def test_singleton(self):
        from app.automation.rate_limiter import get_rate_limiter

        r1 = get_rate_limiter()
        r2 = get_rate_limiter()
        assert r1 is r2

    def test_reset_creates_new_singleton(self):
        from app.automation.rate_limiter import get_rate_limiter

        r1 = get_rate_limiter()
        reset_rate_limiter()
        r2 = get_rate_limiter()
        assert r1 is not r2
