# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pool_health_monitor_wiring.py
"""main.py の Pool Health Monitor opt-in 配線テスト（Asana Task2 / 標準案）。

- ENABLE_POOL_HEALTH_MONITOR=1 なら startup_scheduled_tasks が
  ScheduledTaskManager.start_pool_health_check を呼ぶ
- 未設定（既定 off）なら呼ばれない — 既存環境（dev/staging/production）の
  動作が変わらないことを保証する
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _get_startup_scheduled_tasks_handler():
    """app.main の FastAPI app に登録された startup_scheduled_tasks ハンドラを取得する。"""
    from app.main import app

    for handler in app.router.on_startup:
        if handler.__name__ == "startup_scheduled_tasks":
            return handler
    raise AssertionError("startup_scheduled_tasks handler not found on app.router.on_startup")


@pytest.mark.asyncio
async def test_pool_health_monitor_started_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENABLE_POOL_HEALTH_MONITOR=1 のとき start_pool_health_check が呼ばれる。"""
    monkeypatch.setenv("ENABLE_POOL_HEALTH_MONITOR", "1")
    # 他テスト（test_open_registration.py / test_invitations.py）が
    # os.environ["DISABLE_BACKGROUND_MONITORING"] = "1" をモジュールレベルで
    # 後始末なしに設定するため、フルスイート実行時に汚染されうる。
    # ここでは _is_background_monitoring_enabled() が True になる前提を明示的に保証する。
    monkeypatch.delenv("DISABLE_BACKGROUND_MONITORING", raising=False)
    monkeypatch.delenv("ENABLE_BACKGROUND_MONITORING", raising=False)

    mock_manager = AsyncMock()
    handler = _get_startup_scheduled_tasks_handler()

    with (
        patch(
            "app.automation.scheduled_tasks.get_scheduled_task_manager",
            return_value=mock_manager,
        ),
        patch(
            "app.notifications.config.get_notification_settings",
            return_value=MagicMock(default_channel="test"),
        ),
    ):
        await handler()

    mock_manager.start_pool_health_check.assert_called_once()
    _, kwargs = mock_manager.start_pool_health_check.call_args
    assert "on_error" in kwargs


@pytest.mark.asyncio
async def test_pool_health_monitor_not_started_when_flag_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENABLE_POOL_HEALTH_MONITOR 未設定（既定 off）なら start_pool_health_check は呼ばれない。"""
    monkeypatch.delenv("ENABLE_POOL_HEALTH_MONITOR", raising=False)
    monkeypatch.delenv("DISABLE_BACKGROUND_MONITORING", raising=False)
    monkeypatch.delenv("ENABLE_BACKGROUND_MONITORING", raising=False)

    mock_manager = AsyncMock()
    handler = _get_startup_scheduled_tasks_handler()

    with (
        patch(
            "app.automation.scheduled_tasks.get_scheduled_task_manager",
            return_value=mock_manager,
        ),
        patch(
            "app.notifications.config.get_notification_settings",
            return_value=MagicMock(default_channel="test"),
        ),
    ):
        await handler()

    mock_manager.start_pool_health_check.assert_not_called()
