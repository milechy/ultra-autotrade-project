# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/scheduled_tasks.py

"""
スケジュール実行タスク。

Phase 6 で導入された日次・週次レポートの自動生成を担当する。

- daily_report_loop(): 毎日 00:30 (JST) に日次レポート生成
- weekly_report_loop(): 毎週月曜 01:00 (JST) に週次レポート生成
- rss_fetch_loop(): 30 分ごとに RSS フィード取得・登録
- ScheduledTaskManager: タスクのライフサイクル管理

Pattern: python-async-patterns.md の「Pattern 2: Background Tasks」を適用。
タイムゾーン: Asia/Tokyo (UTC+9) を基準とする（docs/08_automation_rules.md）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from app.automation.jobs import run_daily_jobs, run_weekly_jobs
from app.database import SessionLocal
from app.notifications.schemas import NotificationChannel

logger = logging.getLogger(__name__)

# デフォルトのタイムゾーン（Asia/Tokyo）
DEFAULT_TIMEZONE = ZoneInfo("Asia/Tokyo")

# スケジュール設定（docs/08_automation_rules.md 準拠）
DAILY_REPORT_TIME = time(0, 30)  # 00:30 JST
WEEKLY_REPORT_TIME = time(1, 0)  # 01:00 JST
WEEKLY_REPORT_DAY = 0  # Monday (0 = Monday, 6 = Sunday)

# RSS フェッチ間隔（秒）
RSS_FETCH_INTERVAL_SECONDS = 1800  # 30 分

# DCA 頻度→秒数マッピング
DCA_FREQUENCY_SECONDS = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


def _calculate_seconds_until(
    target_time: time,
    *,
    target_weekday: Optional[int] = None,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    now: Optional[datetime] = None,
) -> float:
    """
    指定時刻までの秒数を計算する。

    Args:
        target_time: 目標時刻 (HH:MM)
        target_weekday: 目標曜日 (0=Monday, 6=Sunday)。None の場合は毎日。
        tz: タイムゾーン
        now: 現在時刻（テスト用）

    Returns:
        float: 目標時刻までの秒数

    Note:
        - 目標時刻が今日/今週すでに過ぎている場合は翌日/翌週の同時刻までの秒数を返す
        - 最小値は 60 秒（重複実行防止）
    """
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    # 今日の目標時刻を計算
    target_dt = datetime.combine(now.date(), target_time, tzinfo=tz)

    if target_weekday is not None:
        # 週次の場合: 次の target_weekday を計算
        days_ahead = target_weekday - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and now >= target_dt:
            # 今日が target_weekday だが時刻を過ぎている
            days_ahead = 7
        target_dt += timedelta(days=days_ahead)
    else:
        # 日次の場合: 今日の時刻を過ぎていたら翌日
        if now >= target_dt:
            target_dt += timedelta(days=1)

    seconds = (target_dt - now).total_seconds()

    # 最小 60 秒（重複実行防止）
    return max(seconds, 60.0)


async def daily_report_loop(
    *,
    channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    日次レポートの定期実行ループ。

    毎日 00:30 (JST) に run_daily_jobs() を実行する。

    Args:
        channel: 通知チャンネル
        tz: タイムゾーン
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting daily report loop (schedule: %s %s)",
        DAILY_REPORT_TIME,
        tz,
    )

    while True:
        try:
            # 次の実行時刻まで待機
            wait_seconds = _calculate_seconds_until(DAILY_REPORT_TIME, tz=tz)
            logger.debug(
                "Waiting %.1f seconds until next daily report",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

            # 日次ジョブ実行
            logger.info("Running daily report job")
            await asyncio.to_thread(run_daily_jobs, channel=channel)
            logger.info("Daily report job completed")

            # 重複実行防止のため少し待機
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Daily report loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in daily report loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 10 分待機後に再試行
            await asyncio.sleep(600)


async def weekly_report_loop(
    *,
    channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    週次レポートの定期実行ループ。

    毎週月曜 01:00 (JST) に run_weekly_jobs() を実行する。

    Args:
        channel: 通知チャンネル
        tz: タイムゾーン
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting weekly report loop (schedule: Monday %s %s)",
        WEEKLY_REPORT_TIME,
        tz,
    )

    while True:
        try:
            # 次の実行時刻まで待機
            wait_seconds = _calculate_seconds_until(
                WEEKLY_REPORT_TIME,
                target_weekday=WEEKLY_REPORT_DAY,
                tz=tz,
            )
            logger.debug(
                "Waiting %.1f seconds until next weekly report",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

            # 週次ジョブ実行
            logger.info("Running weekly report job")
            await asyncio.to_thread(run_weekly_jobs, channel=channel)
            logger.info("Weekly report job completed")

            # 重複実行防止のため少し待機
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Weekly report loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in weekly report loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 10 分待機後に再試行
            await asyncio.sleep(600)


async def rss_fetch_loop(
    *,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    RSS フィード取得の定期実行ループ。

    30 分ごとに RSSFetcher.fetch_and_register() を実行する。

    Args:
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    from app.knowledge.service import KnowledgeService
    from app.rss.fetcher import RSSFetcher

    logger.info(
        "Starting RSS fetch loop (interval: %ds)",
        RSS_FETCH_INTERVAL_SECONDS,
    )

    while True:
        try:
            # インターバル待機
            logger.debug(
                "Waiting %ds until next RSS fetch",
                RSS_FETCH_INTERVAL_SECONDS,
            )
            await asyncio.sleep(RSS_FETCH_INTERVAL_SECONDS)

            # RSS フェッチ実行
            logger.info("Running RSS fetch job")

            def _run_fetch() -> dict[str, int]:
                db = SessionLocal()
                try:
                    service = KnowledgeService()
                    fetcher = RSSFetcher(knowledge_service=service)
                    return fetcher.fetch_and_register(db)
                finally:
                    db.close()

            results = await asyncio.to_thread(_run_fetch)
            logger.info("RSS fetch job completed", extra={"results": results})

            # 重複実行防止のため少し待機
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("RSS fetch loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in RSS fetch loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 10 分待機後に再試行
            await asyncio.sleep(600)


async def dca_loop(
    *,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    DCA（ドルコスト平均法）積立の定期実行ループ。

    DCAConfig.frequency に従った間隔で DCAService.execute() を実行する。

    Args:
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - enabled=False の場合は 60 秒待機してリチェックする
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info("Starting DCA loop")

    while True:
        try:
            from app.dca.config import load_dca_config
            from app.dca.service import DCAService
            from app.exchange.client import DummyExchangeClient
            from app.exchange.service import ExchangeService

            config = load_dca_config()

            if not config.enabled:
                logger.debug("DCA disabled, waiting 60s before recheck")
                await asyncio.sleep(60)
                continue

            interval = DCA_FREQUENCY_SECONDS.get(config.frequency.value, 86400)
            logger.info(
                "DCA loop: symbol=%s, amount_usd=%s, frequency=%s, interval=%ds, dry_run=%s",
                config.symbol,
                config.amount_usd,
                config.frequency.value,
                interval,
                config.dry_run,
            )

            # DCA 実行
            def _run_dca() -> None:
                client = DummyExchangeClient()
                exchange_service = ExchangeService(client=client)
                dca_service = DCAService(exchange_service=exchange_service)
                result = dca_service.execute(config)
                logger.info(
                    "DCA executed: executed=%s, symbol=%s, order_id=%s, message=%s",
                    result.executed,
                    result.symbol,
                    result.order_id,
                    result.message,
                )

            await asyncio.to_thread(_run_dca)

            # インターバル待機
            logger.debug("DCA loop: sleeping %ds until next execution", interval)
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("DCA loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in DCA loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 60 秒待機後に再試行
            await asyncio.sleep(60)


class ScheduledTaskManager:
    """
    スケジュールタスクのライフサイクル管理。

    FastAPI の startup/shutdown イベントと連携して、
    日次・週次レポートタスクの起動・停止を行う。

    Pattern: python-async-patterns.md の「Pattern 4: Timeout and Cancellation」を適用。
    """

    def __init__(self) -> None:
        self._daily_task: Optional[asyncio.Task[None]] = None
        self._weekly_task: Optional[asyncio.Task[None]] = None
        self._rss_task: Optional[asyncio.Task[None]] = None
        self._dca_task: Optional[asyncio.Task[None]] = None
        self._rebalance_task: Optional[asyncio.Task[None]] = None

    @property
    def is_daily_running(self) -> bool:
        """日次レポートタスクが動作中かどうか。"""
        return self._daily_task is not None and not self._daily_task.done()

    @property
    def is_weekly_running(self) -> bool:
        """週次レポートタスクが動作中かどうか。"""
        return self._weekly_task is not None and not self._weekly_task.done()

    @property
    def is_rss_running(self) -> bool:
        """RSS フェッチタスクが動作中かどうか。"""
        return self._rss_task is not None and not self._rss_task.done()

    @property
    def is_dca_running(self) -> bool:
        """DCA タスクが動作中かどうか。"""
        return self._dca_task is not None and not self._dca_task.done()

    @property
    def is_rebalance_running(self) -> bool:
        """リバランスチェックタスクが動作中かどうか。"""
        return self._rebalance_task is not None and not self._rebalance_task.done()

    async def start_daily_reports(
        self,
        *,
        channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        日次レポートタスクを開始する。

        Args:
            channel: 通知チャンネル
            tz: タイムゾーン
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に日次レポートが開始されている場合
        """
        if self.is_daily_running:
            raise RuntimeError("Daily reports already running")

        logger.info("Starting daily report task")

        self._daily_task = asyncio.create_task(
            daily_report_loop(
                channel=channel,
                tz=tz,
                on_error=on_error,
            )
        )

        logger.info("Daily report task started")

    async def start_weekly_reports(
        self,
        *,
        channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        週次レポートタスクを開始する。

        Args:
            channel: 通知チャンネル
            tz: タイムゾーン
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に週次レポートが開始されている場合
        """
        if self.is_weekly_running:
            raise RuntimeError("Weekly reports already running")

        logger.info("Starting weekly report task")

        self._weekly_task = asyncio.create_task(
            weekly_report_loop(
                channel=channel,
                tz=tz,
                on_error=on_error,
            )
        )

        logger.info("Weekly report task started")

    async def stop_daily_reports(self, timeout: float = 5.0) -> None:
        """
        日次レポートタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_daily_running:
            logger.debug("Daily reports not running - nothing to stop")
            return

        logger.info("Stopping daily report task")

        assert self._daily_task is not None  # noqa: S101
        self._daily_task.cancel()

        try:
            await asyncio.wait_for(self._daily_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Daily report task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Daily report task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping daily report task: %s", exc)

        self._daily_task = None
        logger.info("Daily report task stopped")

    async def stop_weekly_reports(self, timeout: float = 5.0) -> None:
        """
        週次レポートタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_weekly_running:
            logger.debug("Weekly reports not running - nothing to stop")
            return

        logger.info("Stopping weekly report task")

        assert self._weekly_task is not None  # noqa: S101
        self._weekly_task.cancel()

        try:
            await asyncio.wait_for(self._weekly_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Weekly report task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Weekly report task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping weekly report task: %s", exc)

        self._weekly_task = None
        logger.info("Weekly report task stopped")

    async def start_rss_fetch(
        self,
        *,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        RSS フェッチタスクを開始する。

        Args:
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に RSS フェッチが開始されている場合
        """
        if self.is_rss_running:
            raise RuntimeError("RSS fetch already running")

        logger.info("Starting RSS fetch task")

        self._rss_task = asyncio.create_task(
            rss_fetch_loop(
                on_error=on_error,
            )
        )

        logger.info("RSS fetch task started")

    async def stop_rss_fetch(self, timeout: float = 5.0) -> None:
        """
        RSS フェッチタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_rss_running:
            logger.debug("RSS fetch not running - nothing to stop")
            return

        logger.info("Stopping RSS fetch task")

        assert self._rss_task is not None  # noqa: S101
        self._rss_task.cancel()

        try:
            await asyncio.wait_for(self._rss_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("RSS fetch task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "RSS fetch task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping RSS fetch task: %s", exc)

        self._rss_task = None
        logger.info("RSS fetch task stopped")

    async def start_dca(
        self,
        *,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        DCA タスクを開始する。

        Args:
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に DCA タスクが開始されている場合
        """
        if self.is_dca_running:
            raise RuntimeError("DCA already running")

        logger.info("Starting DCA task")

        self._dca_task = asyncio.create_task(
            dca_loop(
                on_error=on_error,
            )
        )

        logger.info("DCA task started")

    async def stop_dca(self, timeout: float = 5.0) -> None:
        """
        DCA タスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_dca_running:
            logger.debug("DCA not running - nothing to stop")
            return

        logger.info("Stopping DCA task")

        assert self._dca_task is not None  # noqa: S101
        self._dca_task.cancel()

        try:
            await asyncio.wait_for(self._dca_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("DCA task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "DCA task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping DCA task: %s", exc)

        self._dca_task = None
        logger.info("DCA task stopped")

    async def start_rebalance_check(
        self,
        *,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        リバランスチェックタスクを開始する。

        Args:
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既にリバランスチェックが開始されている場合
        """
        if self.is_rebalance_running:
            raise RuntimeError("Rebalance check already running")

        logger.info("Starting rebalance check task")

        from app.automation.rebalance_job import rebalance_check_loop

        self._rebalance_task = asyncio.create_task(
            rebalance_check_loop(
                on_error=on_error,
            )
        )

        logger.info("Rebalance check task started")

    async def stop_rebalance_check(self, timeout: float = 5.0) -> None:
        """
        リバランスチェックタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_rebalance_running:
            logger.debug("Rebalance check not running - nothing to stop")
            return

        logger.info("Stopping rebalance check task")

        assert self._rebalance_task is not None  # noqa: S101
        self._rebalance_task.cancel()

        try:
            await asyncio.wait_for(self._rebalance_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Rebalance check task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Rebalance check task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping rebalance check task: %s", exc)

        self._rebalance_task = None
        logger.info("Rebalance check task stopped")

    async def stop_all(self, timeout: float = 5.0) -> None:
        """
        全てのスケジュールタスクを停止する。

        Args:
            timeout: 各タスクのキャンセル待機タイムアウト秒数
        """
        logger.info("Stopping all scheduled tasks")

        await asyncio.gather(
            self.stop_daily_reports(timeout=timeout),
            self.stop_weekly_reports(timeout=timeout),
            self.stop_rss_fetch(timeout=timeout),
            self.stop_dca(timeout=timeout),
            self.stop_rebalance_check(timeout=timeout),
            return_exceptions=True,
        )

        logger.info("All scheduled tasks stopped")


# グローバルなタスクマネージャインスタンス
_scheduled_task_manager: Optional[ScheduledTaskManager] = None


def get_scheduled_task_manager() -> ScheduledTaskManager:
    """
    グローバルな ScheduledTaskManager インスタンスを取得する。

    Returns:
        ScheduledTaskManager: タスクマネージャ

    Note:
        - 初回呼び出し時にインスタンスを生成
        - FastAPI の依存性注入で使用可能
    """
    global _scheduled_task_manager
    if _scheduled_task_manager is None:
        _scheduled_task_manager = ScheduledTaskManager()
    return _scheduled_task_manager
