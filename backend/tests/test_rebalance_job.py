# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rebalance_job.py

"""
ScheduledTaskManager のリバランス関連テストと rebalance_check_loop のインポートテスト。
"""

import asyncio
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-rebalance-job")

# app.notifications.composite は未実装のため sys.modules にスタブを登録する
_composite_stub = ModuleType("app.notifications.composite")
_mock_cns_class = MagicMock()
_composite_stub.CompositeNotificationService = _mock_cns_class  # type: ignore[attr-defined]
sys.modules.setdefault("app.notifications.composite", _composite_stub)

# ---------------------------------------------------------------------------
# テスト: rebalance_check_loop がインポートできる
# ---------------------------------------------------------------------------


def test_rebalance_check_loop_can_be_imported() -> None:
    """rebalance_check_loop が app.automation.rebalance_job からインポートできる。"""
    from app.automation.rebalance_job import rebalance_check_loop  # noqa: F401

    assert callable(rebalance_check_loop)


# ---------------------------------------------------------------------------
# テスト: ScheduledTaskManager.is_rebalance_running プロパティ
# ---------------------------------------------------------------------------


def test_is_rebalance_running_default_false() -> None:
    """ScheduledTaskManager 初期状態で is_rebalance_running は False。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    assert manager.is_rebalance_running is False


# ---------------------------------------------------------------------------
# テスト: start_rebalance_check でタスクが作成される
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_rebalance_check_makes_is_running_true() -> None:
    """start_rebalance_check() 後に is_rebalance_running が True になる。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    assert not manager.is_rebalance_running

    await manager.start_rebalance_check()

    try:
        assert manager.is_rebalance_running is True
    finally:
        # 後始末: タスクをキャンセルして他テストに影響しないようにする
        await manager.stop_rebalance_check()


# ---------------------------------------------------------------------------
# テスト: stop_rebalance_check でタスクがキャンセルされる
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_rebalance_check_makes_is_running_false() -> None:
    """stop_rebalance_check() 後に is_rebalance_running が False になる。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    await manager.start_rebalance_check()
    assert manager.is_rebalance_running is True

    await manager.stop_rebalance_check()

    assert manager.is_rebalance_running is False


# ---------------------------------------------------------------------------
# テスト: stop_all にリバランスタスクが含まれる
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_all_includes_rebalance_task() -> None:
    """stop_all() がリバランスタスクも停止する。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    await manager.start_rebalance_check()
    assert manager.is_rebalance_running is True

    # stop_all() で全タスク（リバランスを含む）を停止
    await manager.stop_all()

    assert manager.is_rebalance_running is False


# ---------------------------------------------------------------------------
# テスト: start_rebalance_check が二重起動で RuntimeError を発生させる
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_rebalance_check_raises_if_already_running() -> None:
    """既に起動中の場合 start_rebalance_check() は RuntimeError を発生させる。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    await manager.start_rebalance_check()

    try:
        with pytest.raises(RuntimeError, match="already running"):
            await manager.start_rebalance_check()
    finally:
        await manager.stop_rebalance_check()


# ---------------------------------------------------------------------------
# テスト: 未起動の状態で stop_rebalance_check を呼んでも例外が出ない
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_rebalance_check_when_not_running_is_noop() -> None:
    """未起動の状態で stop_rebalance_check() を呼んでも例外は発生しない。"""
    from app.automation.scheduled_tasks import ScheduledTaskManager

    manager = ScheduledTaskManager()

    # 例外なく完了すること
    await manager.stop_rebalance_check()

    assert manager.is_rebalance_running is False


# ---------------------------------------------------------------------------
# rebalance_check_loop ループ本体のテスト
# ---------------------------------------------------------------------------


class TestRebalanceCheckLoopExecution:
    """rebalance_check_loop の while-loop 本体実行テスト。"""

    @pytest.mark.asyncio
    async def test_run_check_needs_rebalance_true(self) -> None:
        """needs_rebalance=True のとき simulate() と notify() が呼ばれる（L50-116）。"""
        from app.automation.rebalance_job import rebalance_check_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        async def run_in_same_thread(fn: object, *args: object, **kwargs: object) -> object:
            assert callable(fn)
            return fn(*args, **kwargs)  # type: ignore[operator]

        mock_status = MagicMock()
        mock_status.needs_rebalance = True
        mock_status.current_allocations = [MagicMock(deviation_pct=0.15)]

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "test-prop-1"
        mock_proposal.operations = [MagicMock(), MagicMock()]

        mock_service = MagicMock()
        mock_service.get_current_status.return_value = mock_status
        mock_service.simulate.return_value = mock_proposal

        mock_notifier = MagicMock()
        _mock_cns_class.return_value = mock_notifier

        with (
            patch("asyncio.sleep", side_effect=mock_sleep),
            patch("asyncio.to_thread", side_effect=run_in_same_thread),
            patch("app.aave.rebalance_service.RebalanceService", return_value=mock_service),
            patch("app.aave.client.get_default_aave_client"),
            patch("app.aave.config.get_aave_settings"),
            patch("app.aave.rebalance_config.get_rebalance_settings"),
            patch("app.aave.service.AaveService"),
            patch("app.aave.state_manager.get_default_state_manager"),
            patch("app.automation.state.get_monitoring_service"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rebalance_check_loop()

        mock_service.simulate.assert_called_once()
        mock_notifier.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_check_needs_rebalance_false(self) -> None:
        """needs_rebalance=False のとき simulate() は呼ばれない（L80-85）。"""
        from app.automation.rebalance_job import rebalance_check_loop

        sleep_count = 0

        async def mock_sleep(seconds: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        async def run_in_same_thread(fn: object, *args: object, **kwargs: object) -> object:
            assert callable(fn)
            return fn(*args, **kwargs)  # type: ignore[operator]

        mock_status = MagicMock()
        mock_status.needs_rebalance = False
        mock_status.current_allocations = [MagicMock(deviation_pct=0.02)]

        mock_service = MagicMock()
        mock_service.get_current_status.return_value = mock_status

        with (
            patch("asyncio.sleep", side_effect=mock_sleep),
            patch("asyncio.to_thread", side_effect=run_in_same_thread),
            patch("app.aave.rebalance_service.RebalanceService", return_value=mock_service),
            patch("app.aave.client.get_default_aave_client"),
            patch("app.aave.config.get_aave_settings"),
            patch("app.aave.rebalance_config.get_rebalance_settings"),
            patch("app.aave.service.AaveService"),
            patch("app.aave.state_manager.get_default_state_manager"),
            patch("app.automation.state.get_monitoring_service"),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rebalance_check_loop()

        mock_service.simulate.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_calls_on_error_callback(self) -> None:
        """例外発生時に on_error コールバックが呼ばれる（L122-131）。"""
        from app.automation.rebalance_job import rebalance_check_loop

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == 600:  # エラー後の待機 → ここで終了させる
                raise asyncio.CancelledError()

        async def to_thread_raises(fn: object, *args: object, **kwargs: object) -> object:
            raise RuntimeError("simulated _run_check error")

        on_error_calls: list[Exception] = []

        def on_error(exc: Exception) -> None:
            on_error_calls.append(exc)

        with (
            patch("asyncio.sleep", side_effect=mock_sleep),
            patch("asyncio.to_thread", side_effect=to_thread_raises),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rebalance_check_loop(on_error=on_error)

        assert len(on_error_calls) == 1
        assert isinstance(on_error_calls[0], RuntimeError)
        assert 600 in sleep_calls
