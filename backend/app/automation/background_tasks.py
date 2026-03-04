# backend/app/automation/background_tasks.py

"""
バックグラウンド監視タスク。

Phase 5 で導入された継続的監視ループを提供する。

- continuous_monitoring_loop(): 1分ごとにヘルスファクターをチェック
- BackgroundTaskManager: タスクのライフサイクル管理

Pattern: python-async-patterns.md の「Pattern 2: Background Tasks」を適用。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# デフォルトの監視間隔（秒）
DEFAULT_MONITORING_INTERVAL_SECONDS = 60


async def continuous_monitoring_loop(
    get_health_factor_func: Callable[[], Optional[Decimal]],
    on_health_factor: Callable[[Optional[Decimal]], None],
    *,
    interval_seconds: float = DEFAULT_MONITORING_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    継続的なヘルスファクター監視ループ。

    1分ごとに get_health_factor_func() を呼び出し、
    結果を on_health_factor() コールバックに渡す。

    Args:
        get_health_factor_func: ヘルスファクター取得関数（同期）
        on_health_factor: ヘルスファクター取得後のコールバック
                          (MonitoringService.record_health_factor を想定)
        interval_seconds: 監視間隔（秒）
        on_error: エラー発生時のコールバック（省略時はログ出力のみ）

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時も監視は継続（fail-safe）
    """
    logger.info(
        "Starting continuous monitoring loop (interval: %.1fs)",
        interval_seconds,
    )

    while True:
        try:
            # 同期関数をスレッドプールで実行
            hf = await asyncio.to_thread(get_health_factor_func)

            logger.debug(
                "Monitoring check at %s: health_factor=%s",
                datetime.now(timezone.utc).isoformat(),
                hf,
            )

            # コールバックで結果を処理（record_health_factor 等）
            on_health_factor(hf)

        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled - shutting down")
            raise  # 再送出してタスク終了

        except Exception as exc:
            logger.error("Error in monitoring loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は短い待機後に再試行
            await asyncio.sleep(10)
            continue

        # 通常の監視間隔で待機
        await asyncio.sleep(interval_seconds)


class BackgroundTaskManager:
    """
    バックグラウンドタスクのライフサイクル管理。

    FastAPI の startup/shutdown イベントと連携して、
    タスクの起動・停止を行う。

    Pattern: python-async-patterns.md の「Pattern 4: Timeout and Cancellation」を適用。
    """

    def __init__(self) -> None:
        self._monitoring_task: Optional[asyncio.Task[None]] = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        """監視タスクが動作中かどうか。"""
        return self._is_running and self._monitoring_task is not None

    async def start_monitoring(
        self,
        get_health_factor_func: Callable[[], Optional[Decimal]],
        on_health_factor: Callable[[Optional[Decimal]], None],
        *,
        interval_seconds: float = DEFAULT_MONITORING_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        監視タスクを開始する。

        Args:
            get_health_factor_func: ヘルスファクター取得関数
            on_health_factor: 結果処理コールバック
            interval_seconds: 監視間隔
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に監視が開始されている場合
        """
        if self._is_running:
            raise RuntimeError("Monitoring is already running")

        logger.info("Starting background monitoring task")

        self._monitoring_task = asyncio.create_task(
            continuous_monitoring_loop(
                get_health_factor_func=get_health_factor_func,
                on_health_factor=on_health_factor,
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )
        self._is_running = True

        logger.info("Background monitoring task started")

    async def stop_monitoring(self, timeout: float = 5.0) -> None:
        """
        監視タスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数

        Note:
            - タスクをキャンセルし、完了を待機する
            - タイムアウト時は警告を出力するが例外は発生しない
        """
        if not self._is_running or self._monitoring_task is None:
            logger.debug("Monitoring is not running - nothing to stop")
            return

        logger.info("Stopping background monitoring task")

        self._monitoring_task.cancel()

        try:
            await asyncio.wait_for(self._monitoring_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Monitoring task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Monitoring task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping monitoring task: %s", exc)

        self._monitoring_task = None
        self._is_running = False

        logger.info("Background monitoring task stopped")


# グローバルなタスクマネージャインスタンス
# FastAPI の startup/shutdown から参照される
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """
    グローバルな BackgroundTaskManager インスタンスを取得する。

    Returns:
        BackgroundTaskManager: タスクマネージャ

    Note:
        - 初回呼び出し時にインスタンスを生成
        - FastAPI の依存性注入で使用可能
    """
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
