# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Tests for news scheduler safeguard: is_news_stale, record_news_fetch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class TestNewsSchedulerSafeguard:
    """Tests for MonitoringService news tracking methods."""

    def _make_service(self) -> "MonitoringService":  # noqa: F821
        from app.automation.monitoring_service import MonitoringService

        return MonitoringService(enable_state_sync=False)

    def test_initial_last_news_fetched_at_is_none(self) -> None:
        svc = self._make_service()
        assert svc.get_last_news_fetched_at() is None

    def test_is_news_stale_when_never_fetched(self) -> None:
        svc = self._make_service()
        assert svc.is_news_stale() is True

    def test_record_news_fetch_sets_timestamp(self) -> None:
        svc = self._make_service()
        before = datetime.now(timezone.utc)
        svc.record_news_fetch()
        after = datetime.now(timezone.utc)

        ts = svc.get_last_news_fetched_at()
        assert ts is not None
        assert before <= ts <= after

    def test_is_news_stale_false_immediately_after_fetch(self) -> None:
        svc = self._make_service()
        svc.record_news_fetch()
        assert svc.is_news_stale() is False

    def test_is_news_stale_true_after_threshold_exceeded(self) -> None:
        from app.automation.monitoring_service import MonitoringService

        svc = MonitoringService(enable_state_sync=False)
        # Manually set timestamp to 6 hours ago
        old_ts = datetime.now(timezone.utc) - timedelta(hours=6)
        svc._last_news_fetched_at = old_ts  # noqa: SLF001
        assert svc.is_news_stale(threshold_hours=5) is True

    def test_is_news_stale_false_within_threshold(self) -> None:
        from app.automation.monitoring_service import MonitoringService

        svc = MonitoringService(enable_state_sync=False)
        # Set timestamp to 3 hours ago, threshold is 5 hours
        recent_ts = datetime.now(timezone.utc) - timedelta(hours=3)
        svc._last_news_fetched_at = recent_ts  # noqa: SLF001
        assert svc.is_news_stale(threshold_hours=5) is False

    def test_is_news_stale_custom_threshold(self) -> None:
        from app.automation.monitoring_service import MonitoringService

        svc = MonitoringService(enable_state_sync=False)
        # 2 hours old with 1-hour threshold → stale
        svc._last_news_fetched_at = datetime.now(timezone.utc) - timedelta(hours=2)  # noqa: SLF001
        assert svc.is_news_stale(threshold_hours=1) is True

    def test_record_news_fetch_updates_timestamp(self) -> None:
        svc = self._make_service()
        svc.record_news_fetch()
        first_ts = svc.get_last_news_fetched_at()

        svc.record_news_fetch()
        second_ts = svc.get_last_news_fetched_at()

        assert second_ts is not None
        assert first_ts is not None
        assert second_ts >= first_ts
