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


async def proposal_timeout_loop(
    *,
    interval_seconds: int = 300,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    期限切れ Proposal を検出して LINE 通知する定期ループ。

    5 分ごとに pending かつ expires_at が過去の Proposal を検索し、
    canceled に更新して LINE 通知を送る。

    Args:
        interval_seconds: チェック間隔（秒）。デフォルト 300 秒（5 分）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting proposal timeout loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            def _run_timeout_check() -> None:
                import os  # noqa: PLC0415
                from datetime import datetime, timezone  # noqa: PLC0415

                from app.database import SessionLocal  # noqa: PLC0415

                db = SessionLocal()
                try:
                    from app.proposals.models import Proposal  # noqa: PLC0415

                    now = datetime.now(timezone.utc)
                    expired = (
                        db.query(Proposal)
                        .filter(Proposal.status == "pending", Proposal.expires_at < now)
                        .all()
                    )
                    for proposal in expired:
                        try:
                            proposal.status = "canceled"
                            db.flush()
                            logger.info(
                                "Proposal %d expired (op=%s, asset=%s)",
                                proposal.id,
                                proposal.operation,
                                proposal.asset,
                            )
                            if os.getenv("LINE_NOTIFY_TOKEN"):
                                try:
                                    from app.notifications.line_notifier import (  # noqa: PLC0415
                                        notify_proposal_timeout,
                                    )

                                    notify_proposal_timeout(
                                        operation=proposal.operation,
                                        asset=proposal.asset,
                                    )
                                except Exception as _line_exc:
                                    logger.debug("notify_proposal_timeout failed: %s", _line_exc)
                        except Exception as _item_exc:
                            logger.warning(
                                "Failed to cancel proposal %d: %s", proposal.id, _item_exc
                            )
                    if expired:
                        db.commit()
                        logger.info("Canceled %d expired proposals", len(expired))
                except Exception as _db_exc:
                    db.rollback()
                    logger.warning("Proposal timeout check DB error: %s", _db_exc)
                finally:
                    db.close()

            await asyncio.to_thread(_run_timeout_check)

        except asyncio.CancelledError:
            logger.info("Proposal timeout loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in proposal timeout loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


async def health_check_loop(
    *,
    interval_seconds: int = 300,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    HF 並列チェック・ポジション安全確認の定期実行ループ。

    5 分ごとに check_health_factors_concurrent() と check_all_positions_safe() を実行する。

    Args:
        interval_seconds: 取得間隔（秒）。デフォルト 300 秒（5 分）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting health check loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            async def _run_health_check() -> None:
                from app.automation.schemas import ComponentType  # noqa: PLC0415
                from app.automation.state import get_monitoring_service  # noqa: PLC0415

                monitoring_service = get_monitoring_service()

                try:
                    from app.aave.monitor import get_health_factor  # noqa: PLC0415

                    is_safe = await monitoring_service.check_all_positions_safe(get_health_factor)
                    if not is_safe:
                        logger.warning("Position safety check failed: HF below emergency threshold")
                        monitoring_service.record_error(ComponentType.AAVE)
                except Exception as hf_exc:
                    logger.warning("check_all_positions_safe skipped: %s", hf_exc)

            await _run_health_check()

        except asyncio.CancelledError:
            logger.info("Health check loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in health check loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


async def latency_monitor_loop(
    *,
    interval_seconds: int = 60,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    API 応答時間の定期計測ループ。

    1 分ごとに /api/automation/status エンドポイントの応答時間を計測し
    MonitoringService.record_latency() に記録する。

    Args:
        interval_seconds: 計測間隔（秒）。デフォルト 60 秒（1 分）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    import os  # noqa: PLC0415

    logger.info(
        "Starting latency monitor loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            def _run_latency_check() -> None:
                import time  # noqa: PLC0415

                import httpx  # noqa: PLC0415

                from app.automation.schemas import ComponentType  # noqa: PLC0415
                from app.automation.state import get_monitoring_service  # noqa: PLC0415

                base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
                url = f"{base_url}/api/automation/status"

                monitoring_service = get_monitoring_service()
                start = time.monotonic()
                try:
                    httpx.get(url, timeout=35)
                    elapsed = time.monotonic() - start
                    monitoring_service.record_latency(ComponentType.SYSTEM, elapsed)
                    logger.debug("Latency recorded: %.3fs for %s", elapsed, url)
                except Exception as req_exc:
                    logger.warning("Latency check request failed (skipping): %s", req_exc)

            await asyncio.to_thread(_run_latency_check)

        except asyncio.CancelledError:
            logger.info("Latency monitor loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in latency monitor loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


async def process_news_loop(
    *,
    interval_seconds: int = 300,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    POST /automation/process-news を定期実行するループ。

    INTERNAL_API_TOKEN を X-Internal-Token ヘッダーに付与して内部 API を呼ぶ。
    BACKEND_BASE_URL が未設定の場合は http://localhost:8000 を使用。

    Args:
        interval_seconds: 実行間隔（秒）。デフォルト 300 秒（5 分）
        on_error: エラー発生時のコールバック

    Note:
        - INTERNAL_API_TOKEN が未設定の場合はスキップしてログ警告のみ
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    import os  # noqa: PLC0415

    logger.info("Starting process_news_loop (interval: %ds)", interval_seconds)

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            token = os.getenv("INTERNAL_API_TOKEN", "")
            if not token:
                logger.warning("process_news_loop: INTERNAL_API_TOKEN not set, skipping")
                continue

            base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
            url = f"{base_url}/automation/process-news"

            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={"X-Internal-Token": token},
                    timeout=120.0,
                )

            logger.info(
                "process_news_loop: POST %s → %d",
                url,
                resp.status_code,
            )

        except asyncio.CancelledError:
            logger.info("process_news_loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("process_news_loop error: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(60)


async def price_change_monitor_loop(
    *,
    interval_seconds: int = 300,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    24 時間価格変動率の定期取得・記録ループ。

    5 分ごとに ExchangeService.get_price_change_24h() を呼び、
    MonitoringService.record_price_change_24h() に記録する。

    Args:
        interval_seconds: 取得間隔（秒）。デフォルト 300 秒（5 分）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting price change monitor loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            def _run_monitor() -> None:
                from app.automation.state import get_monitoring_service  # noqa: PLC0415
                from app.exchange.client import DummyExchangeClient  # noqa: PLC0415
                from app.exchange.service import ExchangeService  # noqa: PLC0415

                client = DummyExchangeClient()
                exchange_service = ExchangeService(client=client)
                monitoring_service = get_monitoring_service()

                pct = exchange_service.get_price_change_24h()
                if pct is not None:
                    monitoring_service.record_price_change_24h(float(pct))
                    logger.info("price_change_24h recorded: %s", pct)
                else:
                    logger.debug("price_change_24h: no data available, skipping")

            await asyncio.to_thread(_run_monitor)

        except asyncio.CancelledError:
            logger.info("Price change monitor loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in price change monitor loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


async def learning_loop(
    *,
    interval_seconds: int = 21600,  # 6 時間
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    AI継続学習サイクルの定期実行ループ。

    6 時間ごとに AILearningService.run_learning_cycle() を実行する。

    Args:
        interval_seconds: 実行間隔（秒）。デフォルト 21600 秒（6 時間）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - 各ステップは fail-open（AILearningService 内部で try/except 済み）
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting AI learning loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            logger.info("Running AI learning cycle")
            db = SessionLocal()
            try:
                from app.ai.learning_service import AILearningService  # noqa: PLC0415

                svc = AILearningService(db)
                result = await svc.run_learning_cycle()
                logger.info(
                    "AI learning cycle completed at %s",
                    result.completed_at,
                )
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("AI learning loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in AI learning loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 10 分待機後に再試行
            await asyncio.sleep(600)


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
        self._price_monitor_task: Optional[asyncio.Task[None]] = None
        self._health_check_task: Optional[asyncio.Task[None]] = None
        self._latency_monitor_task: Optional[asyncio.Task[None]] = None
        self._proposal_timeout_task: Optional[asyncio.Task[None]] = None
        self._learning_task: Optional[asyncio.Task[None]] = None

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

    @property
    def is_price_monitor_running(self) -> bool:
        """価格変動モニタータスクが動作中かどうか。"""
        return self._price_monitor_task is not None and not self._price_monitor_task.done()

    @property
    def is_health_check_running(self) -> bool:
        """HFヘルスチェックタスクが動作中かどうか。"""
        return self._health_check_task is not None and not self._health_check_task.done()

    @property
    def is_latency_monitor_running(self) -> bool:
        """レイテンシモニタータスクが動作中かどうか。"""
        return self._latency_monitor_task is not None and not self._latency_monitor_task.done()

    @property
    def is_proposal_timeout_running(self) -> bool:
        """期限切れProposalチェックタスクが動作中かどうか。"""
        return self._proposal_timeout_task is not None and not self._proposal_timeout_task.done()

    @property
    def is_learning_running(self) -> bool:
        """AI学習サイクルタスクが動作中かどうか。"""
        return self._learning_task is not None and not self._learning_task.done()

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

    async def start_price_monitor(
        self,
        *,
        interval_seconds: int = 300,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        価格変動モニタータスクを開始する。

        Args:
            interval_seconds: 取得間隔（秒）
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に価格変動モニターが開始されている場合
        """
        if self.is_price_monitor_running:
            raise RuntimeError("Price change monitor already running")

        logger.info("Starting price change monitor task")

        self._price_monitor_task = asyncio.create_task(
            price_change_monitor_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("Price change monitor task started")

    async def stop_price_monitor(self, timeout: float = 5.0) -> None:
        """
        価格変動モニタータスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_price_monitor_running:
            logger.debug("Price change monitor not running - nothing to stop")
            return

        logger.info("Stopping price change monitor task")

        assert self._price_monitor_task is not None  # noqa: S101
        self._price_monitor_task.cancel()

        try:
            await asyncio.wait_for(self._price_monitor_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Price change monitor task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Price change monitor task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping price change monitor task: %s", exc)

        self._price_monitor_task = None
        logger.info("Price change monitor task stopped")

    async def start_proposal_timeout(
        self,
        *,
        interval_seconds: int = 300,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        期限切れProposalチェックタスクを開始する。

        Raises:
            RuntimeError: 既に開始されている場合
        """
        if self.is_proposal_timeout_running:
            raise RuntimeError("Proposal timeout check already running")

        logger.info("Starting proposal timeout task")

        self._proposal_timeout_task = asyncio.create_task(
            proposal_timeout_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("Proposal timeout task started")

    async def stop_proposal_timeout(self, timeout: float = 5.0) -> None:
        """期限切れProposalチェックタスクを停止する。"""
        if not self.is_proposal_timeout_running:
            logger.debug("Proposal timeout check not running - nothing to stop")
            return

        logger.info("Stopping proposal timeout task")

        assert self._proposal_timeout_task is not None  # noqa: S101
        self._proposal_timeout_task.cancel()

        try:
            await asyncio.wait_for(self._proposal_timeout_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Proposal timeout task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Proposal timeout task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping proposal timeout task: %s", exc)

        self._proposal_timeout_task = None
        logger.info("Proposal timeout task stopped")

    async def start_latency_monitor(
        self,
        *,
        interval_seconds: int = 60,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        レイテンシモニタータスクを開始する。

        Args:
            interval_seconds: 計測間隔（秒）
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既にレイテンシモニターが開始されている場合
        """
        if self.is_latency_monitor_running:
            raise RuntimeError("Latency monitor already running")

        logger.info("Starting latency monitor task")

        self._latency_monitor_task = asyncio.create_task(
            latency_monitor_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("Latency monitor task started")

    async def stop_latency_monitor(self, timeout: float = 5.0) -> None:
        """
        レイテンシモニタータスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_latency_monitor_running:
            logger.debug("Latency monitor not running - nothing to stop")
            return

        logger.info("Stopping latency monitor task")

        assert self._latency_monitor_task is not None  # noqa: S101
        self._latency_monitor_task.cancel()

        try:
            await asyncio.wait_for(self._latency_monitor_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Latency monitor task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Latency monitor task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping latency monitor task: %s", exc)

        self._latency_monitor_task = None
        logger.info("Latency monitor task stopped")

    async def start_health_check(
        self,
        *,
        interval_seconds: int = 300,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        HFヘルスチェックタスクを開始する。

        Args:
            interval_seconds: チェック間隔（秒）
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既にヘルスチェックが開始されている場合
        """
        if self.is_health_check_running:
            raise RuntimeError("Health check already running")

        logger.info("Starting health check task")

        self._health_check_task = asyncio.create_task(
            health_check_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("Health check task started")

    async def stop_health_check(self, timeout: float = 5.0) -> None:
        """
        HFヘルスチェックタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_health_check_running:
            logger.debug("Health check not running - nothing to stop")
            return

        logger.info("Stopping health check task")

        assert self._health_check_task is not None  # noqa: S101
        self._health_check_task.cancel()

        try:
            await asyncio.wait_for(self._health_check_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Health check task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Health check task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping health check task: %s", exc)

        self._health_check_task = None
        logger.info("Health check task stopped")

    async def start_learning(
        self,
        *,
        interval_seconds: int = 21600,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        AI学習サイクルタスクを開始する。

        Args:
            interval_seconds: 実行間隔（秒）。デフォルト 21600 秒（6 時間）
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に学習タスクが開始されている場合
        """
        if self.is_learning_running:
            raise RuntimeError("AI learning already running")

        logger.info("Starting AI learning task")

        self._learning_task = asyncio.create_task(
            learning_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("AI learning task started")

    async def stop_learning(self, timeout: float = 5.0) -> None:
        """
        AI学習サイクルタスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_learning_running:
            logger.debug("AI learning not running - nothing to stop")
            return

        logger.info("Stopping AI learning task")

        assert self._learning_task is not None  # noqa: S101
        self._learning_task.cancel()

        try:
            await asyncio.wait_for(self._learning_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("AI learning task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "AI learning task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping AI learning task: %s", exc)

        self._learning_task = None
        logger.info("AI learning task stopped")

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
            self.stop_price_monitor(timeout=timeout),
            self.stop_health_check(timeout=timeout),
            self.stop_latency_monitor(timeout=timeout),
            self.stop_proposal_timeout(timeout=timeout),
            self.stop_learning(timeout=timeout),
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
