# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_background_tasks.py

"""
バックグラウンド監視タスクのユニットテスト。

python-async-patterns.md の「Pattern 8: Testing Async Code」に準拠。
"""

import asyncio
from decimal import Decimal
from typing import Optional

import pytest

from app.automation.background_tasks import (
    BackgroundTaskManager,
    continuous_monitoring_loop,
    get_task_manager,
)


@pytest.mark.asyncio
async def test_continuous_monitoring_loop_calls_health_factor():
    """監視ループがヘルスファクター取得関数を呼び出すことを確認。"""
    call_count = 0
    recorded_values = []

    def mock_get_hf() -> Optional[Decimal]:
        nonlocal call_count
        call_count += 1
        return Decimal("2.0")

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        recorded_values.append(hf)

    # 監視ループを短時間だけ実行
    task = asyncio.create_task(
        continuous_monitoring_loop(
            get_health_factor_func=mock_get_hf,
            on_health_factor=mock_on_hf,
            interval_seconds=0.1,  # 100ms 間隔
        )
    )

    # 少し待機してからキャンセル
    await asyncio.sleep(0.25)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # 少なくとも1回は呼ばれているはず
    assert call_count >= 1
    assert len(recorded_values) >= 1
    assert recorded_values[0] == Decimal("2.0")


@pytest.mark.asyncio
async def test_continuous_monitoring_loop_handles_error():
    """監視ループがエラー発生時にコールバックを呼び出すことを確認。"""
    call_count = 0
    error_count = 0
    error_messages = []

    def mock_get_hf() -> Optional[Decimal]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Test error")
        return Decimal("1.9")

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        pass

    def mock_on_error(exc: Exception) -> None:
        nonlocal error_count
        error_count += 1
        error_messages.append(str(exc))

    task = asyncio.create_task(
        continuous_monitoring_loop(
            get_health_factor_func=mock_get_hf,
            on_health_factor=mock_on_hf,
            interval_seconds=0.05,
            on_error=mock_on_error,
        )
    )

    # 最初の呼び出しでエラーが発生するまで待つ
    await asyncio.sleep(0.15)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # エラーが1回発生したことを確認
    assert error_count == 1
    assert "Test error" in error_messages[0]
    # 少なくとも1回は呼び出されたはず
    assert call_count >= 1


@pytest.mark.asyncio
async def test_background_task_manager_start_stop():
    """BackgroundTaskManager の start/stop が正しく動作することを確認。"""
    manager = BackgroundTaskManager()

    assert not manager.is_running

    def mock_get_hf() -> Optional[Decimal]:
        return Decimal("2.0")

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        pass

    await manager.start_monitoring(
        get_health_factor_func=mock_get_hf,
        on_health_factor=mock_on_hf,
        interval_seconds=1.0,
    )

    assert manager.is_running

    await manager.stop_monitoring()

    assert not manager.is_running


@pytest.mark.asyncio
async def test_background_task_manager_start_raises_if_already_running():
    """既に実行中の場合に start_monitoring が例外を発生することを確認。"""
    manager = BackgroundTaskManager()

    def mock_get_hf() -> Optional[Decimal]:
        return Decimal("2.0")

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        pass

    await manager.start_monitoring(
        get_health_factor_func=mock_get_hf,
        on_health_factor=mock_on_hf,
        interval_seconds=1.0,
    )

    with pytest.raises(RuntimeError, match="already running"):
        await manager.start_monitoring(
            get_health_factor_func=mock_get_hf,
            on_health_factor=mock_on_hf,
        )

    await manager.stop_monitoring()


@pytest.mark.asyncio
async def test_background_task_manager_stop_does_nothing_if_not_running():
    """実行中でない場合に stop_monitoring が何もしないことを確認。"""
    manager = BackgroundTaskManager()

    assert not manager.is_running

    # 例外なく完了するはず
    await manager.stop_monitoring()

    assert not manager.is_running


def test_get_task_manager_returns_singleton():
    """get_task_manager がシングルトンを返すことを確認。"""
    manager1 = get_task_manager()
    manager2 = get_task_manager()

    assert manager1 is manager2


@pytest.mark.asyncio
async def test_continuous_monitoring_loop_records_none_hf():
    """監視ループが HF=None を正しく記録することを確認。

    HF=None は「借入なし（ポジションなし）」を意味し、
    state.json の更新には必要。スキップしてはいけない。
    """
    recorded_values = []

    def mock_get_hf() -> Optional[Decimal]:
        # 借入なしの場合は None を返す
        return None

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        # この関数が None でも呼ばれることを確認
        recorded_values.append(hf)

    task = asyncio.create_task(
        continuous_monitoring_loop(
            get_health_factor_func=mock_get_hf,
            on_health_factor=mock_on_hf,
            interval_seconds=0.1,
        )
    )

    await asyncio.sleep(0.25)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # HF=None でもコールバックが呼ばれていることを確認
    assert len(recorded_values) >= 1
    assert recorded_values[0] is None  # None が記録されている


@pytest.mark.asyncio
async def test_continuous_monitoring_loop_records_mixed_values():
    """監視ループが HF 値と None の両方を正しく記録することを確認。"""
    call_count = 0
    recorded_values = []

    def mock_get_hf() -> Optional[Decimal]:
        nonlocal call_count
        call_count += 1
        # 最初は None、次は値を返す
        if call_count == 1:
            return None
        return Decimal("2.0")

    def mock_on_hf(hf: Optional[Decimal]) -> None:
        recorded_values.append(hf)

    task = asyncio.create_task(
        continuous_monitoring_loop(
            get_health_factor_func=mock_get_hf,
            on_health_factor=mock_on_hf,
            interval_seconds=0.1,
        )
    )

    await asyncio.sleep(0.35)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # None と値の両方が記録されていることを確認
    assert len(recorded_values) >= 2
    assert recorded_values[0] is None
    assert recorded_values[1] == Decimal("2.0")