# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_scheduler_watchdog.py
"""スケジューラー Watchdog のテスト。"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-watchdog")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.automation.scheduler_watchdog import (  # noqa: E402
    compute_scheduler_health,
    scheduler_watchdog_loop,
)


# ---------------------------------------------------------------------------
# compute_scheduler_health — pure function tests
# ---------------------------------------------------------------------------


def test_healthy_when_last_run_is_none():
    """`last_run` が None の場合は healthy（起動直後は楽観的 OK）。"""
    result = compute_scheduler_health(None, interval_hours=4)
    assert result["healthy"] is True
    assert result["overdue_hours"] is None
    assert result["reason"] is None


def test_healthy_when_last_run_is_recent():
    """最後の実行が interval * 2 以内なら healthy。"""
    recent = datetime.now(timezone.utc) - timedelta(hours=3)
    result = compute_scheduler_health(recent.isoformat(), interval_hours=4)
    assert result["healthy"] is True


def test_overdue_when_last_run_exceeds_threshold():
    """最後の実行が interval * 2 を超えたら unhealthy。"""
    old = datetime.now(timezone.utc) - timedelta(hours=9)  # 4h * 2 = 8h < 9h
    result = compute_scheduler_health(old.isoformat(), interval_hours=4)
    assert result["healthy"] is False
    assert result["overdue_hours"] is not None
    assert result["overdue_hours"] >= 9.0
    assert result["reason"] is not None


def test_exactly_at_threshold_is_healthy():
    """interval * 2 ちょうどはまだ healthy。"""
    at_threshold = datetime.now(timezone.utc) - timedelta(hours=8, seconds=-30)
    result = compute_scheduler_health(at_threshold.isoformat(), interval_hours=4)
    assert result["healthy"] is True


def test_invalid_iso_string_returns_healthy():
    """パース不能な文字列は healthy として扱う（安全側フォールバック）。"""
    result = compute_scheduler_health("not-a-date", interval_hours=4)
    assert result["healthy"] is True


# ---------------------------------------------------------------------------
# scheduler_watchdog_loop — async tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_calls_on_overdue_when_scheduler_overdue():
    """overdue 状態のとき on_overdue コールバックが呼ばれること。"""
    overdue_msgs: list[str] = []

    def fake_on_overdue(msg: str) -> None:
        overdue_msgs.append(msg)

    old_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    fake_status = {
        "running": True,
        "last_run": old_time,
        "next_run": None,
        "last_error": None,
    }

    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise asyncio.CancelledError

    with (
        patch("app.automation.scheduler_watchdog.get_scheduler_status", return_value=fake_status),
        patch("app.automation.scheduler_watchdog._send_watchdog_slack"),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch.dict(os.environ, {"AI_JUDGMENT_INTERVAL_HOURS": "4"}),
    ):
        try:
            await scheduler_watchdog_loop(
                check_interval_seconds=1800,
                on_overdue=fake_on_overdue,
            )
        except asyncio.CancelledError:
            pass

    assert len(overdue_msgs) >= 1
    assert "Watchdog" in overdue_msgs[0]


@pytest.mark.asyncio
async def test_watchdog_does_not_call_on_overdue_when_healthy():
    """健全なスケジューラーでは on_overdue が呼ばれないこと。"""
    overdue_msgs: list[str] = []

    def fake_on_overdue(msg: str) -> None:
        overdue_msgs.append(msg)

    recent_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    fake_status = {
        "running": True,
        "last_run": recent_time,
        "next_run": None,
        "last_error": None,
    }

    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise asyncio.CancelledError

    with (
        patch("app.automation.scheduler_watchdog.get_scheduler_status", return_value=fake_status),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch.dict(os.environ, {"AI_JUDGMENT_INTERVAL_HOURS": "4"}),
    ):
        try:
            await scheduler_watchdog_loop(
                check_interval_seconds=1800,
                on_overdue=fake_on_overdue,
            )
        except asyncio.CancelledError:
            pass

    assert len(overdue_msgs) == 0


@pytest.mark.asyncio
async def test_watchdog_skips_check_when_scheduler_not_running():
    """スケジューラーが無効（running=False）のとき on_overdue が呼ばれないこと。"""
    overdue_msgs: list[str] = []
    old_time = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    fake_status = {"running": False, "last_run": old_time, "next_run": None, "last_error": None}

    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise asyncio.CancelledError

    with (
        patch("app.automation.scheduler_watchdog.get_scheduler_status", return_value=fake_status),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await scheduler_watchdog_loop(on_overdue=lambda m: overdue_msgs.append(m))
        except asyncio.CancelledError:
            pass

    assert len(overdue_msgs) == 0


@pytest.mark.asyncio
async def test_watchdog_on_overdue_failure_does_not_crash_loop():
    """on_overdue コールバックが例外を投げても、ループが継続すること。"""
    check_count = 0
    old_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    fake_status = {"running": True, "last_run": old_time, "next_run": None, "last_error": None}

    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 4:
            raise asyncio.CancelledError

    def bad_callback(msg: str) -> None:
        nonlocal check_count
        check_count += 1
        raise ValueError("callback failure")

    with (
        patch("app.automation.scheduler_watchdog.get_scheduler_status", return_value=fake_status),
        patch("app.automation.scheduler_watchdog._send_watchdog_slack"),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch.dict(os.environ, {"AI_JUDGMENT_INTERVAL_HOURS": "4"}),
    ):
        try:
            await scheduler_watchdog_loop(check_interval_seconds=1800, on_overdue=bad_callback)
        except asyncio.CancelledError:
            pass

    # ループは継続しているはず
    assert sleep_count >= 4


@pytest.mark.asyncio
async def test_watchdog_slack_failure_does_not_crash_loop():
    """Slack 通知が失敗してもループが継続すること。"""
    old_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    fake_status = {"running": True, "last_run": old_time, "next_run": None, "last_error": None}

    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 3:
            raise asyncio.CancelledError

    with (
        patch("app.automation.scheduler_watchdog.get_scheduler_status", return_value=fake_status),
        patch(
            "app.automation.scheduler_watchdog._send_watchdog_slack",
            side_effect=Exception("slack down"),
        ),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch.dict(os.environ, {"AI_JUDGMENT_INTERVAL_HOURS": "4"}),
    ):
        try:
            await scheduler_watchdog_loop()
        except asyncio.CancelledError:
            pass

    assert sleep_count >= 3
