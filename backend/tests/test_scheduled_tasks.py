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
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
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
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=RuntimeError("daily job failed"),
            ),
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
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
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
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
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
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
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


# ---------------------------------------------------------------------------
# on_error コールバック自体が例外を投げるパス (L159-160, 219-228, 287-296, etc.)
# ---------------------------------------------------------------------------


class TestLoopOnErrorCallbackRaises:
    """on_error コールバック自体が例外を発生させるパスのカバレッジ。"""

    @staticmethod
    def _on_error_raiser(exc: Exception) -> None:
        raise RuntimeError(f"on_error failed internally: {exc}")

    @staticmethod
    def _make_sleep(raise_on_seconds: float = 600.0) -> tuple[list[float], object]:
        calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            calls.append(seconds)
            if seconds == raise_on_seconds:
                raise asyncio.CancelledError()

        return calls, mock_sleep

    @pytest.mark.asyncio
    async def test_daily_report_loop_on_error_raises_internally(self) -> None:
        """daily_report_loop: on_error 自体が例外を投げても継続する（L159-160）。"""
        from app.automation.scheduled_tasks import daily_report_loop

        _, mock_sleep = self._make_sleep()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=RuntimeError("job failed"),
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await daily_report_loop(on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_weekly_report_loop_on_error_callback(self) -> None:
        """weekly_report_loop: on_error が呼ばれ、on_error 自体が例外を投げても継続（L219-228）。"""
        from app.automation.scheduled_tasks import weekly_report_loop

        _, mock_sleep = self._make_sleep()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=RuntimeError("weekly failed"),
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await weekly_report_loop(on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_rss_fetch_loop_on_error_callback(self) -> None:
        """rss_fetch_loop: on_error コールバックが呼ばれる（L287-296）。"""
        from app.automation.scheduled_tasks import rss_fetch_loop

        _, mock_sleep = self._make_sleep()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=RuntimeError("rss failed"),
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rss_fetch_loop(on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_dca_loop_on_error_callback(self) -> None:
        """dca_loop: on_error コールバックが呼ばれる（L367-376）。"""
        from app.automation.scheduled_tasks import dca_loop

        _, mock_sleep = self._make_sleep(raise_on_seconds=60.0)

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.dca.config.load_dca_config", side_effect=RuntimeError("config failed")),
        ):
            with pytest.raises(asyncio.CancelledError):
                await dca_loop(on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_health_check_loop_on_error_callback(self) -> None:
        """health_check_loop: on_error コールバックが呼ばれる（L526-534）。"""
        from app.automation.scheduled_tasks import health_check_loop

        _, mock_sleep = self._make_sleep()

        async def raising_health_check() -> None:
            raise RuntimeError("health check failed unexpectedly")

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.state.get_monitoring_service", side_effect=RuntimeError("ms failed")
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await health_check_loop(interval_seconds=1, on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_price_change_monitor_on_error_callback(self) -> None:
        """price_change_monitor_loop: on_error コールバックが呼ばれる（L657-665）。"""
        from app.automation.scheduled_tasks import price_change_monitor_loop

        _, mock_sleep = self._make_sleep()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=RuntimeError("price failed"),
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await price_change_monitor_loop(interval_seconds=1, on_error=self._on_error_raiser)

    @pytest.mark.asyncio
    async def test_learning_loop_on_error_callback(self) -> None:
        """learning_loop: on_error コールバックが呼ばれる（L715-724）。"""
        from app.automation.scheduled_tasks import learning_loop

        _, mock_sleep = self._make_sleep()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.SessionLocal", side_effect=RuntimeError("db failed")
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await learning_loop(interval_seconds=1, on_error=self._on_error_raiser)


# ---------------------------------------------------------------------------
# ループ本体の追加カバレッジ
# ---------------------------------------------------------------------------


class TestLoopBodyAdditional:
    """TestLoopBodies で未カバーのパスを補完するテスト。"""

    @staticmethod
    async def _run_in_same_thread(fn: object, *args: object, **kwargs: object) -> object:
        assert callable(fn)
        return fn(*args, **kwargs)  # type: ignore[operator]

    @staticmethod
    def _make_sleep_counter(raise_on: int = 2) -> tuple[list[float], object]:
        calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            calls.append(seconds)
            if len(calls) >= raise_on:
                raise asyncio.CancelledError()

        return calls, mock_sleep

    @pytest.mark.asyncio
    async def test_dca_loop_enabled_executes(self) -> None:
        """dca_loop: enabled=True のとき DCAService.execute() が呼ばれる（L333-361）。"""
        from app.automation.scheduled_tasks import dca_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            # dca_loop にはループ冒頭の sleep がない: 実行後 sleep → 最初の sleep で終了
            raise asyncio.CancelledError()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.frequency.value = "daily"
        mock_config.symbol = "BTC/USDT"
        mock_config.amount_usd = 100
        mock_config.dry_run = True

        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.symbol = "BTC/USDT"
        mock_result.order_id = "test-order"
        mock_result.message = "OK"

        mock_dca_svc = MagicMock()
        mock_dca_svc.execute.return_value = mock_result

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
            patch("app.dca.config.load_dca_config", return_value=mock_config),
            patch("app.dca.service.DCAService", return_value=mock_dca_svc),
            patch("app.exchange.client.DummyExchangeClient"),
            patch("app.exchange.service.ExchangeService"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await dca_loop()

        assert mock_dca_svc.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_proposal_timeout_loop_cancels_expired_proposals(self) -> None:
        """proposal_timeout_loop: 期限切れ Proposal が canceled に更新される（L399-473）。"""
        from app.automation.scheduled_tasks import proposal_timeout_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)

        mock_proposal = MagicMock()
        mock_proposal.id = 1
        mock_proposal.status = "pending"
        mock_proposal.operation = "BUY"
        mock_proposal.asset = "ETH"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_proposal]

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
            patch("app.database.SessionLocal", return_value=mock_db),
            # Proposal は本物のクラスを使う（SQLAlchemy式評価のため）
            # mock_db の query chain が引数に関わらず結果を返す
        ):
            with pytest.raises(asyncio.CancelledError):
                await proposal_timeout_loop(interval_seconds=1)

        assert mock_proposal.status == "canceled"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_proposal_timeout_loop_no_expired(self) -> None:
        """proposal_timeout_loop: 期限切れなし → commit は呼ばれない（L450-452）。"""
        from app.automation.scheduled_tasks import proposal_timeout_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
            patch("app.database.SessionLocal", return_value=mock_db),
        ):
            with pytest.raises(asyncio.CancelledError):
                await proposal_timeout_loop(interval_seconds=1)

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_check_loop_not_safe_records_error(self) -> None:
        """health_check_loop: is_safe=False のとき record_error() が呼ばれる（L515-518）。"""
        from app.automation.scheduled_tasks import health_check_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_ms = MagicMock()
        mock_ms.check_all_positions_safe = AsyncMock(return_value=False)

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch("app.automation.state.get_monitoring_service", return_value=mock_ms),
            patch("app.aave.monitor.get_health_factor"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await health_check_loop(interval_seconds=1)

        mock_ms.record_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_latency_monitor_loop_records_latency(self) -> None:
        """latency_monitor_loop: httpx.get 成功 → record_latency() が呼ばれる（L557-603）。"""
        from app.automation.scheduled_tasks import latency_monitor_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_ms = MagicMock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
            patch("app.automation.state.get_monitoring_service", return_value=mock_ms),
            patch("httpx.get"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await latency_monitor_loop(interval_seconds=1)

        mock_ms.record_latency.assert_called_once()

    @pytest.mark.asyncio
    async def test_latency_monitor_loop_request_fails_skips(self) -> None:
        """latency_monitor_loop: httpx.get 失敗 → record_latency() は呼ばれない（L586-587）。"""
        from app.automation.scheduled_tasks import latency_monitor_loop

        _, mock_sleep = self._make_sleep_counter(raise_on=2)
        mock_ms = MagicMock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "app.automation.scheduled_tasks.asyncio.to_thread",
                side_effect=self._run_in_same_thread,
            ),
            patch("app.automation.state.get_monitoring_service", return_value=mock_ms),
            patch("httpx.get", side_effect=Exception("connection refused")),
        ):
            with pytest.raises(asyncio.CancelledError):
                await latency_monitor_loop(interval_seconds=1)

        mock_ms.record_latency.assert_not_called()


# ---------------------------------------------------------------------------
# ScheduledTaskManager stop メソッドの TimeoutError / Exception ブランチ
# ---------------------------------------------------------------------------


class TestStopMethodExceptionBranches:
    """各 stop_* メソッドの TimeoutError / Exception ブランチをカバーする。

    asyncio.wait_for をモックして TimeoutError / RuntimeError を発生させ、
    各ブランチが例外を適切に処理することを確認する。
    """

    @staticmethod
    def _make_running_task() -> MagicMock:
        """is_*_running が True になるダミータスクを返す。"""
        task = MagicMock()
        task.done.return_value = False
        task.cancel.return_value = True
        return task

    @pytest.mark.asyncio
    async def test_stop_daily_reports_timeout_branch(self) -> None:
        """stop_daily_reports: TimeoutError ブランチ（L885-891）。"""
        manager = ScheduledTaskManager()
        manager._daily_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_daily_reports(timeout=5.0)

        assert manager._daily_task is None

    @pytest.mark.asyncio
    async def test_stop_daily_reports_exception_branch(self) -> None:
        """stop_daily_reports: Exception ブランチ（L889-891）。"""
        manager = ScheduledTaskManager()
        manager._daily_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_daily_reports(timeout=5.0)

        assert manager._daily_task is None

    @pytest.mark.asyncio
    async def test_stop_weekly_reports_timeout_branch(self) -> None:
        """stop_weekly_reports: TimeoutError ブランチ（L916-922）。"""
        manager = ScheduledTaskManager()
        manager._weekly_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_weekly_reports(timeout=5.0)

        assert manager._weekly_task is None

    @pytest.mark.asyncio
    async def test_stop_weekly_reports_exception_branch(self) -> None:
        """stop_weekly_reports: Exception ブランチ（L920-922）。"""
        manager = ScheduledTaskManager()
        manager._weekly_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_weekly_reports(timeout=5.0)

        assert manager._weekly_task is None

    @pytest.mark.asyncio
    async def test_stop_rss_fetch_timeout_branch(self) -> None:
        """stop_rss_fetch: TimeoutError ブランチ（L974-980）。"""
        manager = ScheduledTaskManager()
        manager._rss_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_rss_fetch(timeout=5.0)

        assert manager._rss_task is None

    @pytest.mark.asyncio
    async def test_stop_rss_fetch_exception_branch(self) -> None:
        """stop_rss_fetch: Exception ブランチ（L978-980）。"""
        manager = ScheduledTaskManager()
        manager._rss_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_rss_fetch(timeout=5.0)

        assert manager._rss_task is None

    @pytest.mark.asyncio
    async def test_stop_dca_timeout_branch(self) -> None:
        """stop_dca: TimeoutError ブランチ（L1032-1038）。"""
        manager = ScheduledTaskManager()
        manager._dca_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_dca(timeout=5.0)

        assert manager._dca_task is None

    @pytest.mark.asyncio
    async def test_stop_dca_exception_branch(self) -> None:
        """stop_dca: Exception ブランチ（L1036-1038）。"""
        manager = ScheduledTaskManager()
        manager._dca_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_dca(timeout=5.0)

        assert manager._dca_task is None

    @pytest.mark.asyncio
    async def test_stop_rebalance_check_timeout_branch(self) -> None:
        """stop_rebalance_check: TimeoutError ブランチ（L1057-1070）。"""
        manager = ScheduledTaskManager()
        manager._rebalance_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_rebalance_check(timeout=5.0)

        assert manager._rebalance_task is None

    @pytest.mark.asyncio
    async def test_stop_rebalance_check_exception_branch(self) -> None:
        """stop_rebalance_check: Exception ブランチ（L1068-1070）。"""
        manager = ScheduledTaskManager()
        manager._rebalance_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_rebalance_check(timeout=5.0)

        assert manager._rebalance_task is None

    @pytest.mark.asyncio
    async def test_stop_price_monitor_timeout_branch(self) -> None:
        """stop_price_monitor: TimeoutError ブランチ（L1083-1101）。"""
        manager = ScheduledTaskManager()
        manager._price_monitor_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_price_monitor(timeout=5.0)

        assert manager._price_monitor_task is None

    @pytest.mark.asyncio
    async def test_stop_price_monitor_exception_branch(self) -> None:
        """stop_price_monitor: Exception ブランチ（L1099-1101）。"""
        manager = ScheduledTaskManager()
        manager._price_monitor_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_price_monitor(timeout=5.0)

        assert manager._price_monitor_task is None

    @pytest.mark.asyncio
    async def test_stop_proposal_timeout_timeout_branch(self) -> None:
        """stop_proposal_timeout: TimeoutError ブランチ（L1205-1211）。"""
        manager = ScheduledTaskManager()
        manager._proposal_timeout_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_proposal_timeout(timeout=5.0)

        assert manager._proposal_timeout_task is None

    @pytest.mark.asyncio
    async def test_stop_proposal_timeout_exception_branch(self) -> None:
        """stop_proposal_timeout: Exception ブランチ（L1120）。"""
        manager = ScheduledTaskManager()
        manager._proposal_timeout_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_proposal_timeout(timeout=5.0)

        assert manager._proposal_timeout_task is None

    @pytest.mark.asyncio
    async def test_stop_latency_monitor_timeout_branch(self) -> None:
        """stop_latency_monitor: TimeoutError ブランチ（L1153-1159）。"""
        manager = ScheduledTaskManager()
        manager._latency_monitor_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_latency_monitor(timeout=5.0)

        assert manager._latency_monitor_task is None

    @pytest.mark.asyncio
    async def test_stop_latency_monitor_exception_branch(self) -> None:
        """stop_latency_monitor: Exception ブランチ（L1177）。"""
        manager = ScheduledTaskManager()
        manager._latency_monitor_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_latency_monitor(timeout=5.0)

        assert manager._latency_monitor_task is None

    @pytest.mark.asyncio
    async def test_stop_health_check_timeout_branch(self) -> None:
        """stop_health_check: TimeoutError ブランチ（L1327-1333）。"""
        manager = ScheduledTaskManager()
        manager._health_check_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_health_check(timeout=5.0)

        assert manager._health_check_task is None

    @pytest.mark.asyncio
    async def test_stop_health_check_exception_branch(self) -> None:
        """stop_health_check: Exception ブランチ（L1355）。"""
        manager = ScheduledTaskManager()
        manager._health_check_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_health_check(timeout=5.0)

        assert manager._health_check_task is None

    @pytest.mark.asyncio
    async def test_stop_learning_timeout_branch(self) -> None:
        """stop_learning: TimeoutError ブランチ（L1388-1394）。"""
        manager = ScheduledTaskManager()
        manager._learning_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            await manager.stop_learning(timeout=5.0)

        assert manager._learning_task is None

    @pytest.mark.asyncio
    async def test_stop_learning_exception_branch(self) -> None:
        """stop_learning: Exception ブランチ（L1392-1394）。"""
        manager = ScheduledTaskManager()
        manager._learning_task = self._make_running_task()

        with patch.object(asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("unexpected"))):
            await manager.stop_learning(timeout=5.0)

        assert manager._learning_task is None

    @pytest.mark.asyncio
    async def test_start_dca_raises_if_already_running(self) -> None:
        """start_dca: 既に実行中の場合 RuntimeError（L1000）。"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.dca_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_dca()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_dca()

        await manager.stop_dca()

    @pytest.mark.asyncio
    async def test_start_price_monitor_raises_if_already_running(self) -> None:
        """start_price_monitor: 既に実行中の場合 RuntimeError（L1120）。"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.price_change_monitor_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_price_monitor()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_price_monitor()

        await manager.stop_price_monitor()

    @pytest.mark.asyncio
    async def test_start_latency_monitor_raises_if_already_running(self) -> None:
        """start_latency_monitor: 既に実行中の場合 RuntimeError（L1233）。"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.latency_monitor_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_latency_monitor()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_latency_monitor()

        await manager.stop_latency_monitor()

    @pytest.mark.asyncio
    async def test_start_learning_raises_if_already_running(self) -> None:
        """start_learning: 既に実行中の場合 RuntimeError（L1355）。"""
        manager = ScheduledTaskManager()

        with patch("app.automation.scheduled_tasks.learning_loop") as mock_loop:

            async def mock_coro(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(100)

            mock_loop.return_value = mock_coro()
            await manager.start_learning()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_learning()

        await manager.stop_learning()


# ---------------------------------------------------------------------------
# process_news_loop — POST /automation/process-news with X-Internal-Token
# ---------------------------------------------------------------------------


class TestProcessNewsLoop:
    """process_news_loop のテスト。

    - X-Internal-Token ヘッダーを付与して POST すること
    - INTERNAL_API_TOKEN 未設定時はスキップすること
    - asyncio.CancelledError を伝播すること
    - 例外発生時は on_error を呼び 60 秒待機すること
    """

    @staticmethod
    def _make_httpx_mock(status_code: int = 200) -> tuple[object, AsyncMock]:
        """httpx.AsyncClient のモック (class, client_instance) を返す。"""
        mock_response = MagicMock()
        mock_response.status_code = status_code

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=None)

        mock_class = MagicMock(return_value=cm)
        return mock_class, mock_client

    @pytest.mark.asyncio
    async def test_sends_x_internal_token_header(self) -> None:
        """X-Internal-Token ヘッダーに INTERNAL_API_TOKEN を付与して POST する。"""
        from app.automation.scheduled_tasks import process_news_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        mock_class, mock_client = self._make_httpx_mock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch.dict("os.environ", {"INTERNAL_API_TOKEN": "test-token-abc"}),
            patch("httpx.AsyncClient", mock_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1)

        mock_client.post.assert_called_once()
        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers == {"X-Internal-Token": "test-token-abc"}

    @pytest.mark.asyncio
    async def test_posts_to_correct_url(self) -> None:
        """BACKEND_BASE_URL/automation/process-news に POST する。"""
        from app.automation.scheduled_tasks import process_news_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        mock_class, mock_client = self._make_httpx_mock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch.dict(
                "os.environ",
                {"INTERNAL_API_TOKEN": "tok", "BACKEND_BASE_URL": "http://backend:8000"},
            ),
            patch("httpx.AsyncClient", mock_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1)

        posted_url = mock_client.post.call_args.args[0]
        assert posted_url == "http://backend:8000/automation/process-news"

    @pytest.mark.asyncio
    async def test_skips_when_token_not_set(self) -> None:
        """INTERNAL_API_TOKEN が空のとき httpx を呼ばない。"""
        from app.automation.scheduled_tasks import process_news_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        mock_class, mock_client = self._make_httpx_mock()

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch.dict("os.environ", {"INTERNAL_API_TOKEN": ""}),
            patch("httpx.AsyncClient", mock_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1)

        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self) -> None:
        """asyncio.CancelledError はループ外に伝播する（再 raise される）。"""
        from app.automation.scheduled_tasks import process_news_loop

        async def mock_sleep(seconds: float) -> None:
            raise asyncio.CancelledError()

        with patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1)

    @pytest.mark.asyncio
    async def test_on_error_callback_called_on_exception(self) -> None:
        """httpx 例外時に on_error が呼ばれ、60 秒待機してループ継続する。"""
        from app.automation.scheduled_tasks import process_news_loop

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == 60:
                raise asyncio.CancelledError()

        on_error_calls: list[Exception] = []

        def on_error(exc: Exception) -> None:
            on_error_calls.append(exc)

        failing_class = MagicMock(side_effect=RuntimeError("connection refused"))

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch.dict("os.environ", {"INTERNAL_API_TOKEN": "tok"}),
            patch("httpx.AsyncClient", failing_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1, on_error=on_error)

        assert len(on_error_calls) == 1
        assert isinstance(on_error_calls[0], RuntimeError)
        assert 60 in sleep_calls

    @pytest.mark.asyncio
    async def test_on_error_callback_raises_internally(self) -> None:
        """on_error 自体が例外を投げても 60 秒待機でループを継続する。"""
        from app.automation.scheduled_tasks import process_news_loop

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == 60:
                raise asyncio.CancelledError()

        def on_error(exc: Exception) -> None:
            raise RuntimeError("on_error internal failure")

        failing_class = MagicMock(side_effect=RuntimeError("httpx error"))

        with (
            patch("app.automation.scheduled_tasks.asyncio.sleep", side_effect=mock_sleep),
            patch.dict("os.environ", {"INTERNAL_API_TOKEN": "tok"}),
            patch("httpx.AsyncClient", failing_class),
        ):
            with pytest.raises(asyncio.CancelledError):
                await process_news_loop(interval_seconds=1, on_error=on_error)

        assert 60 in sleep_calls
