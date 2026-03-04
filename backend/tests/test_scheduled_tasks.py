# backend/tests/test_scheduled_tasks.py

"""
スケジュールタスクのユニットテスト。

python-async-patterns.md の「Pattern 8: Testing Async Code」に準拠。
"""

import asyncio
from datetime import datetime, time
from unittest.mock import patch
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
