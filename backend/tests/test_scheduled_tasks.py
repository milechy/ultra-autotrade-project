# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_scheduled_tasks.py

"""
スケジュールタスクのユニットテスト。

python-async-patterns.md の「Pattern 8: Testing Async Code」に準拠。
"""

import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.automation.scheduled_tasks import (
    DAILY_REPORT_TIME,
    WEEKLY_REPORT_DAY,
    WEEKLY_REPORT_TIME,
    ScheduledTaskManager,
    _calculate_seconds_until,
    get_scheduled_task_manager,
)


class TestCalculateSecondsUntil:
    """_calculate_seconds_until 関数のテスト"""

    def test_daily_future_time_today(self):
        """今日の未来時刻までの秒数を計算"""
        tz = ZoneInfo("Asia/Tokyo")
        now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=tz)  # 10:00 JST
        target = time(12, 0)  # 12:00

        seconds = _calculate_seconds_until(target, tz=tz, now=now)

        # 2時間 = 7200秒
        assert seconds == 7200.0

    def test_daily_past_time_today_schedules_tomorrow(self):
        """今日の過去時刻の場合は翌日を計算"""
        tz = ZoneInfo("Asia/Tokyo")
        now = datetime(2025, 1, 15, 14, 0, 0, tzinfo=tz)  # 14:00 JST
        target = time(12, 0)  # 12:00

        seconds = _calculate_seconds_until(target, tz=tz, now=now)

        # 翌日 12:00 まで = 22時間 = 79200秒
        assert seconds == 79200.0

    def test_weekly_future_weekday(self):
        """今週の未来曜日までの秒数を計算"""
        tz = ZoneInfo("Asia/Tokyo")
        # 2025-01-15 は水曜日 (weekday=2)
        now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=tz)
        target = time(1, 0)  # 01:00
        target_weekday = 0  # Monday

        seconds = _calculate_seconds_until(target, target_weekday=target_weekday, tz=tz, now=now)

        # 次の月曜 01:00 まで (2025-01-20 01:00)
        # 水曜 10:00 → 月曜 01:00 = 4日15時間 = 111時間 = 399600秒
        assert seconds == 399600.0

    def test_weekly_same_weekday_future_time(self):
        """同じ曜日で未来時刻の場合は今週を計算"""
        tz = ZoneInfo("Asia/Tokyo")
        # 2025-01-13 は月曜日 (weekday=0)
        now = datetime(2025, 1, 13, 0, 30, 0, tzinfo=tz)  # 00:30 Monday
        target = time(1, 0)  # 01:00
        target_weekday = 0  # Monday

        seconds = _calculate_seconds_until(target, target_weekday=target_weekday, tz=tz, now=now)

        # 30分後 = 1800秒
        assert seconds == 1800.0

    def test_weekly_same_weekday_past_time(self):
        """同じ曜日で過去時刻の場合は翌週を計算"""
        tz = ZoneInfo("Asia/Tokyo")
        # 2025-01-13 は月曜日 (weekday=0)
        now = datetime(2025, 1, 13, 2, 0, 0, tzinfo=tz)  # 02:00 Monday
        target = time(1, 0)  # 01:00
        target_weekday = 0  # Monday

        seconds = _calculate_seconds_until(target, target_weekday=target_weekday, tz=tz, now=now)

        # 翌週月曜 01:00 まで = 7日 - 1時間 = 167時間 = 601200秒
        assert seconds == 601200.0

    def test_minimum_60_seconds(self):
        """最小値が60秒であることを確認"""
        tz = ZoneInfo("Asia/Tokyo")
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=tz)
        target = time(12, 0, 30)  # 30秒後

        seconds = _calculate_seconds_until(target, tz=tz, now=now)

        # 30秒だが最小60秒
        assert seconds == 60.0

    def test_naive_datetime_assumed_as_tz(self):
        """naive datetime がタイムゾーン付きとして扱われることを確認"""
        tz = ZoneInfo("Asia/Tokyo")
        now = datetime(2025, 1, 15, 10, 0, 0)  # naive
        target = time(12, 0)

        seconds = _calculate_seconds_until(target, tz=tz, now=now)

        # タイムゾーンが適用され 2時間後
        assert seconds == 7200.0


class TestScheduledTaskManager:
    """ScheduledTaskManager クラスのテスト"""

    @pytest.mark.asyncio
    async def test_start_stop_daily_reports(self):
        """日次レポートタスクの開始・停止"""
        manager = ScheduledTaskManager()

        assert not manager.is_daily_running

        with patch("app.automation.scheduled_tasks.daily_report_loop") as mock_loop:
            # 即座に終了する async generator をモック
            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)  # 長時間待機（キャンセルされる）

            mock_loop.return_value = mock_coro()

            await manager.start_daily_reports()

            assert manager.is_daily_running

        await manager.stop_daily_reports()

        assert not manager.is_daily_running

    @pytest.mark.asyncio
    async def test_start_stop_weekly_reports(self):
        """週次レポートタスクの開始・停止"""
        manager = ScheduledTaskManager()

        assert not manager.is_weekly_running

        with patch("app.automation.scheduled_tasks.weekly_report_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_weekly_reports()

            assert manager.is_weekly_running

        await manager.stop_weekly_reports()

        assert not manager.is_weekly_running

    @pytest.mark.asyncio
    async def test_start_daily_raises_if_already_running(self):
        """既に実行中の場合に例外が発生することを確認"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.daily_report_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_daily_reports()

            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_daily_reports()

        await manager.stop_daily_reports()

    @pytest.mark.asyncio
    async def test_start_weekly_raises_if_already_running(self):
        """既に実行中の場合に例外が発生することを確認"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.weekly_report_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_weekly_reports()

            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_weekly_reports()

        await manager.stop_weekly_reports()

    @pytest.mark.asyncio
    async def test_stop_all(self):
        """全タスクの停止"""
        manager = ScheduledTaskManager()

        with (
            patch("app.automation.scheduled_tasks.daily_report_loop") as mock_daily,
            patch("app.automation.scheduled_tasks.weekly_report_loop") as mock_weekly,
        ):

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_daily.return_value = mock_coro()
            mock_weekly.return_value = mock_coro()

            await manager.start_daily_reports()
            await manager.start_weekly_reports()

            assert manager.is_daily_running
            assert manager.is_weekly_running

            await manager.stop_all()

            assert not manager.is_daily_running
            assert not manager.is_weekly_running

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_running(self):
        """実行中でない場合は何もしない"""
        manager = ScheduledTaskManager()

        assert not manager.is_daily_running
        assert not manager.is_weekly_running

        # 例外なく完了するはず
        await manager.stop_daily_reports()
        await manager.stop_weekly_reports()
        await manager.stop_all()

        assert not manager.is_daily_running
        assert not manager.is_weekly_running


class TestGetScheduledTaskManager:
    """get_scheduled_task_manager 関数のテスト"""

    def test_returns_singleton(self):
        """シングルトンインスタンスを返すことを確認"""
        manager1 = get_scheduled_task_manager()
        manager2 = get_scheduled_task_manager()

        assert manager1 is manager2


class TestScheduleConstants:
    """スケジュール定数のテスト"""

    def test_daily_report_time(self):
        """日次レポート時刻が 00:30 であることを確認"""
        assert DAILY_REPORT_TIME == time(0, 30)

    def test_weekly_report_time(self):
        """週次レポート時刻が 01:00 であることを確認"""
        assert WEEKLY_REPORT_TIME == time(1, 0)

    def test_weekly_report_day_is_monday(self):
        """週次レポート曜日が月曜であることを確認"""
        assert WEEKLY_REPORT_DAY == 0  # Monday


# ---------------------------------------------------------------------------
# Task 2: health_check_loop (check_health_factors_concurrent + check_all_positions_safe)
# ---------------------------------------------------------------------------


class TestHealthCheckLoop:
    """health_check_loop 関連のテスト"""

    @pytest.mark.asyncio
    async def test_start_stop_health_check(self):
        """HFヘルスチェックタスクの開始・停止"""
        manager = ScheduledTaskManager()

        assert not manager.is_health_check_running

        with patch("app.automation.scheduled_tasks.health_check_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_health_check()
            assert manager.is_health_check_running

        await manager.stop_health_check()
        assert not manager.is_health_check_running

    @pytest.mark.asyncio
    async def test_start_health_check_raises_if_already_running(self):
        """既に実行中の場合に例外が発生することを確認"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.health_check_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_health_check()

            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_health_check()

        await manager.stop_health_check()


# ---------------------------------------------------------------------------
# Task 3: latency_monitor_loop (record_latency)
# ---------------------------------------------------------------------------


class TestLatencyMonitorLoop:
    """latency_monitor_loop 関連のテスト"""

    @pytest.mark.asyncio
    async def test_start_stop_latency_monitor(self):
        """レイテンシモニタータスクの開始・停止"""
        manager = ScheduledTaskManager()

        assert not manager.is_latency_monitor_running

        with patch("app.automation.scheduled_tasks.latency_monitor_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_latency_monitor()
            assert manager.is_latency_monitor_running

        await manager.stop_latency_monitor()
        assert not manager.is_latency_monitor_running


# ---------------------------------------------------------------------------
# Task 6 (proposal_timeout): proposal_timeout_loop
# ---------------------------------------------------------------------------


class TestProposalTimeoutLoop:
    """proposal_timeout_loop 関連のテスト"""

    @pytest.mark.asyncio
    async def test_start_stop_proposal_timeout(self):
        """期限切れProposalチェックタスクの開始・停止"""
        manager = ScheduledTaskManager()

        assert not manager.is_proposal_timeout_running

        with patch("app.automation.scheduled_tasks.proposal_timeout_loop") as mock_loop:

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()

            await manager.start_proposal_timeout()
            assert manager.is_proposal_timeout_running

        await manager.stop_proposal_timeout()
        assert not manager.is_proposal_timeout_running

    @pytest.mark.asyncio
    async def test_stop_all_includes_new_tasks(self):
        """stop_all が health_check, latency_monitor, proposal_timeout も停止することを確認"""
        manager = ScheduledTaskManager()

        with (
            patch("app.automation.scheduled_tasks.health_check_loop") as mock_hc,
            patch("app.automation.scheduled_tasks.latency_monitor_loop") as mock_lat,
            patch("app.automation.scheduled_tasks.proposal_timeout_loop") as mock_prop,
        ):

            async def mock_coro(*args, **kwargs):
                await asyncio.sleep(100)

            mock_hc.return_value = mock_coro()
            mock_lat.return_value = mock_coro()
            mock_prop.return_value = mock_coro()

            await manager.start_health_check()
            await manager.start_latency_monitor()
            await manager.start_proposal_timeout()

            assert manager.is_health_check_running
            assert manager.is_latency_monitor_running
            assert manager.is_proposal_timeout_running

            await manager.stop_all()

            assert not manager.is_health_check_running
            assert not manager.is_latency_monitor_running
            assert not manager.is_proposal_timeout_running


# ---------------------------------------------------------------------------
# P1-1 regression: loops must use shared get_monitoring_service() singleton
# ---------------------------------------------------------------------------


class TestMonitoringServiceSingletonUsage:
    """各ループが MonitoringService() を直接インスタンス化せず
    get_monitoring_service() シングルトンを使うことを確認するリグレッションテスト。"""

    @pytest.mark.asyncio
    async def test_health_check_loop_uses_shared_monitoring_service(self):
        """health_check_loop が get_monitoring_service() を呼ぶこと（MonitoringService() 直接生成しない）。"""
        from app.automation.scheduled_tasks import health_check_loop

        calls: list[str] = []
        mock_ms = MagicMock()
        mock_ms.check_all_positions_safe = AsyncMock(return_value=True)

        sleep_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError

        def fake_get_ms() -> MagicMock:
            calls.append("get_monitoring_service")
            return mock_ms

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=fake_sleep),
            patch("app.automation.state.get_monitoring_service", side_effect=fake_get_ms),
        ):
            try:
                await health_check_loop(interval_seconds=1)
            except asyncio.CancelledError:
                pass

        assert "get_monitoring_service" in calls, (
            "health_check_loop must call get_monitoring_service() not MonitoringService()"
        )

    @pytest.mark.asyncio
    async def test_price_monitor_loop_uses_shared_monitoring_service(self):
        """price_monitor_loop が get_monitoring_service() を呼ぶこと（MonitoringService() 直接生成しない）。"""
        from app.automation.scheduled_tasks import price_change_monitor_loop

        calls: list[str] = []
        mock_ms = MagicMock()

        sleep_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError

        def fake_get_ms() -> MagicMock:
            calls.append("get_monitoring_service")
            return mock_ms

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=fake_sleep),
            patch("app.automation.state.get_monitoring_service", side_effect=fake_get_ms),
        ):
            try:
                await price_change_monitor_loop(interval_seconds=1)
            except asyncio.CancelledError:
                pass

        assert "get_monitoring_service" in calls, (
            "price_change_monitor_loop must call get_monitoring_service() not MonitoringService()"
        )


# ---------------------------------------------------------------------------
# ループ本体実行テスト: 各 loop が実際にジョブを呼ぶことを確認
# ---------------------------------------------------------------------------


class TestLoopBodies:
    """各ループ関数の while-loop 本体が実行されることを確認するテスト群。"""

    @staticmethod
    def _make_sleep_counter(raise_on: int = 2) -> tuple[list[float], object]:
        """sleep コールを記録し、指定回数目に CancelledError を発生させるモックを返す。"""
        calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            calls.append(seconds)
            if len(calls) >= raise_on:
                raise asyncio.CancelledError()

        return calls, mock_sleep

    @staticmethod
    async def _run_in_same_thread(fn: object, *args: object, **kwargs: object) -> object:
        assert callable(fn)
        return fn(*args, **kwargs)  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_daily_report_loop_calls_run_daily_jobs(self) -> None:
        """daily_report_loop: スリープ後に run_daily_jobs() が呼ばれる（L126-163）。"""
        from app.automation.scheduled_tasks import daily_report_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_run_daily = MagicMock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.asyncio.to_thread", side_effect=self._run_in_same_thread),
            patch("app.automation.scheduled_tasks.run_daily_jobs", mock_run_daily),
        ):
            with pytest.raises(asyncio.CancelledError):
                await daily_report_loop()

        mock_run_daily.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_report_loop_on_error_callback(self) -> None:
        """daily_report_loop: run_daily_jobs() が例外を投げると on_error が呼ばれる（L154-163）。"""
        from app.automation.scheduled_tasks import daily_report_loop

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == 600:
                raise asyncio.CancelledError()

        on_error_calls: list[Exception] = []

        def on_error(exc: Exception) -> None:
            on_error_calls.append(exc)

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.asyncio.to_thread", side_effect=RuntimeError("daily job failed")),
        ):
            with pytest.raises(asyncio.CancelledError):
                await daily_report_loop(on_error=on_error)

        assert len(on_error_calls) == 1
        assert isinstance(on_error_calls[0], RuntimeError)

    @pytest.mark.asyncio
    async def test_weekly_report_loop_calls_run_weekly_jobs(self) -> None:
        """weekly_report_loop: スリープ後に run_weekly_jobs() が呼ばれる（L187-228）。"""
        from app.automation.scheduled_tasks import weekly_report_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_run_weekly = MagicMock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.asyncio.to_thread", side_effect=self._run_in_same_thread),
            patch("app.automation.scheduled_tasks.run_weekly_jobs", mock_run_weekly),
        ):
            with pytest.raises(asyncio.CancelledError):
                await weekly_report_loop()

        mock_run_weekly.assert_called_once()

    @pytest.mark.asyncio
    async def test_rss_fetch_loop_calls_fetcher(self) -> None:
        """rss_fetch_loop: fetch_and_register() が呼ばれる（L248-296）。"""
        from app.automation.scheduled_tasks import rss_fetch_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_fetcher_instance = MagicMock()
        mock_fetcher_instance.fetch_and_register.return_value = {"registered": 1}

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.asyncio.to_thread", side_effect=self._run_in_same_thread),
            patch("app.knowledge.service.KnowledgeService"),
            patch("app.rss.fetcher.RSSFetcher", return_value=mock_fetcher_instance),
            patch("app.automation.scheduled_tasks.SessionLocal"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rss_fetch_loop()

        mock_fetcher_instance.fetch_and_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_loop_body_runs(self) -> None:
        """health_check_loop: check_all_positions_safe() が呼ばれる（L500-534）。"""
        from unittest.mock import AsyncMock  # noqa: PLC0415

        from app.automation.scheduled_tasks import health_check_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_ms = MagicMock()
        mock_ms.check_all_positions_safe = AsyncMock(return_value=True)

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.state.get_monitoring_service", return_value=mock_ms),
            patch("app.aave.monitor.get_health_factor"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await health_check_loop(interval_seconds=1)

        mock_ms.check_all_positions_safe.assert_called_once()

    @pytest.mark.asyncio
    async def test_price_change_monitor_loop_body_runs(self) -> None:
        """price_change_monitor_loop: get_price_change_24h() と record_price_change_24h() が呼ばれる（L631-665）。"""
        from decimal import Decimal  # noqa: PLC0415

        from app.automation.scheduled_tasks import price_change_monitor_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_ms = MagicMock()
        mock_exchange_svc = MagicMock()
        mock_exchange_svc.get_price_change_24h.return_value = Decimal("1.5")

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.asyncio.to_thread", side_effect=self._run_in_same_thread),
            patch("app.automation.state.get_monitoring_service", return_value=mock_ms),
            patch("app.exchange.service.ExchangeService", return_value=mock_exchange_svc),
            patch("app.exchange.client.DummyExchangeClient"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await price_change_monitor_loop(interval_seconds=1)

        mock_exchange_svc.get_price_change_24h.assert_called_once()
        mock_ms.record_price_change_24h.assert_called_once_with(1.5)

    @pytest.mark.asyncio
    async def test_learning_loop_body_runs(self) -> None:
        """learning_loop: AILearningService.run_learning_cycle() が呼ばれる（L688-724）。"""
        from unittest.mock import AsyncMock  # noqa: PLC0415

        from app.automation.scheduled_tasks import learning_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_result = MagicMock()
        mock_result.completed_at = "2026-01-01T00:00:00Z"
        mock_svc = MagicMock()
        mock_svc.run_learning_cycle = AsyncMock(return_value=mock_result)
        mock_svc_class = MagicMock(return_value=mock_svc)

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.scheduled_tasks.SessionLocal"),
            patch("app.ai.learning_service.AILearningService", mock_svc_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await learning_loop(interval_seconds=1)

        mock_svc.run_learning_cycle.assert_called_once()

    @pytest.mark.asyncio
    async def test_dca_loop_disabled_skips_execution(self) -> None:
        """dca_loop: enabled=False のとき DCAService.execute() は呼ばれない（L317-331）。"""
        from app.automation.scheduled_tasks import dca_loop

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                raise asyncio.CancelledError()

        mock_config = MagicMock()
        mock_config.enabled = False
        mock_dca_svc = MagicMock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.dca.config.load_dca_config", return_value=mock_config),
            patch("app.dca.service.DCAService", return_value=mock_dca_svc),
            patch("app.exchange.client.DummyExchangeClient"),
            patch("app.exchange.service.ExchangeService"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await dca_loop()

        mock_dca_svc.execute.assert_not_called()
        # 60s の待機が入る
        assert 60 in sleep_calls


# ---------------------------------------------------------------------------
# ScheduledTaskManager start/stop — 未カバーのメソッド
# ---------------------------------------------------------------------------


class TestScheduledTaskManagerExtended:
    """start_rss_fetch / stop_rss_fetch / start_dca / stop_dca / start/stop_price_monitor。"""

    @pytest.mark.asyncio
    async def test_start_stop_rss_fetch(self) -> None:
        """RSS フェッチタスクの開始・停止。"""
        manager = ScheduledTaskManager()
        assert not manager.is_rss_running

        with patch("app.automation.scheduled_tasks.rss_fetch_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_rss_fetch()
            assert manager.is_rss_running

        await manager.stop_rss_fetch()
        assert not manager.is_rss_running

    @pytest.mark.asyncio
    async def test_start_rss_fetch_raises_if_already_running(self) -> None:
        """既に実行中は RuntimeError。"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.rss_fetch_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_rss_fetch()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_rss_fetch()

        await manager.stop_rss_fetch()

    @pytest.mark.asyncio
    async def test_start_stop_dca(self) -> None:
        """DCA タスクの開始・停止。"""
        manager = ScheduledTaskManager()
        assert not manager.is_dca_running

        with patch("app.automation.scheduled_tasks.dca_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_dca()
            assert manager.is_dca_running

        await manager.stop_dca()
        assert not manager.is_dca_running

    @pytest.mark.asyncio
    async def test_start_stop_price_monitor(self) -> None:
        """価格変動モニタータスクの開始・停止。"""
        manager = ScheduledTaskManager()
        assert not manager.is_price_monitor_running

        with patch("app.automation.scheduled_tasks.price_change_monitor_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_price_monitor()
            assert manager.is_price_monitor_running

        await manager.stop_price_monitor()
        assert not manager.is_price_monitor_running

    @pytest.mark.asyncio
    async def test_start_stop_learning(self) -> None:
        """AI 学習タスクの開始・停止。"""
        manager = ScheduledTaskManager()
        assert not manager.is_learning_running

        with patch("app.automation.scheduled_tasks.learning_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_learning()
            assert manager.is_learning_running

        await manager.stop_learning()
        assert not manager.is_learning_running

    @pytest.mark.asyncio
    async def test_stop_daily_reports_timeout(self) -> None:
        """stop_daily_reports: タスクがタイムアウトしても例外が出ない（L885-891）。"""
        manager = ScheduledTaskManager()

        # キャンセルに反応しないタスクを作成
        async def never_ends() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                # CancelledError を無視してタイムアウトを引き起こす
                await asyncio.sleep(9999)

        manager._daily_task = asyncio.create_task(never_ends())
        # タイムアウト 0.05s で停止（TimeoutError branch を踏む）
        await manager.stop_daily_reports(timeout=0.05)
        assert not manager.is_daily_running

    @pytest.mark.asyncio
    async def test_stop_weekly_reports_timeout(self) -> None:
        """stop_weekly_reports: タスクがタイムアウトしても例外が出ない（L916-922）。"""
        manager = ScheduledTaskManager()

        async def never_ends() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                await asyncio.sleep(9999)

        manager._weekly_task = asyncio.create_task(never_ends())
        await manager.stop_weekly_reports(timeout=0.05)
        assert not manager.is_weekly_running
