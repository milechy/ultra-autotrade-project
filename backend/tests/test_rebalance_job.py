# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rebalance_job.py

"""
ScheduledTaskManager のリバランス関連テストと rebalance_check_loop のインポートテスト。
"""

import pytest

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
