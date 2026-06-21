# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_oracle_monitor_wiring.py
"""oracle_monitor_loop の配線テスト（接続監査 #3 / OracleMonitor scheduler 結線）。

- ORACLE_MONITOR_FEEDS のパース（valid / 空 / 不正 JSON / 非list / キー欠落）
- フィード未設定なら loop は OracleMonitor を作らず即終了する（dormant）
- フィードありなら check_once を呼び、emergency 発火をログする
- ScheduledTaskManager の start/stop 配線
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---- _build_oracle_feeds_from_env ----


def test_build_feeds_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.automation.scheduled_tasks import _build_oracle_feeds_from_env

    monkeypatch.setenv(
        "ORACLE_MONITOR_FEEDS",
        json.dumps(
            [
                {"name": "USDC", "feed_address": "0xaaa", "rpc_url": "https://rpc"},
                {"name": "WETH", "feed_address": "0xbbb", "rpc_url": "https://rpc"},
            ]
        ),
    )
    feeds = _build_oracle_feeds_from_env()
    assert [f.name for f in feeds] == ["USDC", "WETH"]
    assert feeds[0].feed_address == "0xaaa"


def test_build_feeds_empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.automation.scheduled_tasks import _build_oracle_feeds_from_env

    monkeypatch.delenv("ORACLE_MONITOR_FEEDS", raising=False)
    assert _build_oracle_feeds_from_env() == []


def test_build_feeds_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.automation.scheduled_tasks import _build_oracle_feeds_from_env

    monkeypatch.setenv("ORACLE_MONITOR_FEEDS", "{not json")
    assert _build_oracle_feeds_from_env() == []


def test_build_feeds_non_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.automation.scheduled_tasks import _build_oracle_feeds_from_env

    monkeypatch.setenv("ORACLE_MONITOR_FEEDS", json.dumps({"name": "x"}))
    assert _build_oracle_feeds_from_env() == []


def test_build_feeds_skips_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.automation.scheduled_tasks import _build_oracle_feeds_from_env

    monkeypatch.setenv(
        "ORACLE_MONITOR_FEEDS",
        json.dumps(
            [
                {"name": "ok", "feed_address": "0x1", "rpc_url": "u"},
                {"name": "broken"},  # missing keys → skipped
            ]
        ),
    )
    feeds = _build_oracle_feeds_from_env()
    assert [f.name for f in feeds] == ["ok"]


# ---- oracle_monitor_loop ----


@pytest.mark.asyncio
async def test_loop_no_feeds_returns_without_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    """フィード未設定なら OracleMonitor を構築せず即終了する（dormant）。"""
    from app.automation.scheduled_tasks import oracle_monitor_loop

    with (
        patch("app.automation.scheduled_tasks._build_oracle_feeds_from_env", return_value=[]),
        patch("app.automation.oracle_monitor.OracleMonitor") as mock_monitor_cls,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await oracle_monitor_loop(interval_seconds=1)

    mock_monitor_cls.assert_not_called()
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_loop_with_feeds_calls_check_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """フィードありなら check_once を呼び、emergency 発火を検出する。"""
    from app.automation.scheduled_tasks import oracle_monitor_loop

    report = MagicMock()
    report.anomaly_detected = True
    report.emergency_triggered = True
    report.fetch_failures = []
    report.reasons = ["USDC: stale"]

    mock_monitor = MagicMock()
    mock_monitor.check_once = MagicMock(return_value=report)

    fake_feed = MagicMock()

    with (
        patch(
            "app.automation.scheduled_tasks._build_oracle_feeds_from_env",
            return_value=[fake_feed],
        ),
        patch("app.automation.oracle_monitor.OracleMonitor", return_value=mock_monitor) as mock_cls,
        patch("app.automation.state.get_monitoring_service", return_value=MagicMock()),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        with pytest.raises(asyncio.CancelledError):
            await oracle_monitor_loop(interval_seconds=1)

    mock_cls.assert_called_once()
    mock_monitor.check_once.assert_called_once()


# ---- ScheduledTaskManager start/stop ----


@pytest.mark.asyncio
async def test_manager_start_stop_oracle_monitor() -> None:
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()
    assert not manager.is_oracle_monitor_running

    with patch(
        "app.automation.scheduled_tasks.oracle_monitor_loop", new_callable=AsyncMock
    ) as mock_loop:
        mock_loop.return_value = None
        await manager.start_oracle_monitor(interval_seconds=300)
        assert manager.is_oracle_monitor_running

        await manager.stop_oracle_monitor()
        assert not manager.is_oracle_monitor_running
