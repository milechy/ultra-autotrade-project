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
import json
import logging
import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional
from zoneinfo import ZoneInfo

from app.automation.jobs import run_daily_jobs, run_weekly_jobs
from app.database import SessionLocal
from app.notifications.schemas import NotificationChannel

if TYPE_CHECKING:
    from app.automation.oracle_monitor import OracleFeedConfig

logger = logging.getLogger(__name__)

# デフォルトのタイムゾーン（Asia/Tokyo）
DEFAULT_TIMEZONE = ZoneInfo("Asia/Tokyo")

# スケジュール設定（docs/08_automation_rules.md 準拠）
DAILY_REPORT_TIME = time(0, 30)  # 00:30 JST
WEEKLY_REPORT_TIME = time(1, 0)  # 01:00 JST
WEEKLY_REPORT_DAY = 0  # Monday (0 = Monday, 6 = Sunday)
MONTHLY_FEE_BATCH_TIME = time(9, 0)  # 毎月1日 09:00 JST
MONTHLY_LINE_REPORT_TIME = time(10, 0)  # 毎月1日 10:00 JST (手数料バッチ完了後)

# RSS フェッチ間隔（秒）
RSS_FETCH_INTERVAL_SECONDS = 1800  # 30 分

# リワード自動 Claim チェック間隔（秒）— 毎日 03:00 UTC
REWARD_AUTO_CLAIM_INTERVAL_SECONDS = 86400  # 24 時間
REWARD_AUTO_CLAIM_UTC_HOUR = 3  # 03:00 UTC

# 複合リスク監視間隔（秒）
COMPOUND_RISK_INTERVAL_SECONDS = 600  # 10 分
ORACLE_MONITOR_INTERVAL_SECONDS = 300  # 5 分（oracle staleness は短周期で監視）

# プール赤字監視間隔（秒）
# ENABLE_POOL_HEALTH_MONITOR=1 設定時のみ有効（main.py lifespan 配線は human 承認 PR が必要）
POOL_HEALTH_CHECK_INTERVAL_SECONDS = 3600  # 1 時間

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


def _calculate_seconds_until_month_first(
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    now: Optional[datetime] = None,
) -> float:
    """次回「月初 09:00 JST」までの秒数を返す。

    今月1日 09:00 JST がまだ来ていなければそれを目標とし、
    過ぎていれば翌月1日 09:00 JST を目標とする。
    """
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    this_month_first = datetime(
        now.year,
        now.month,
        1,
        MONTHLY_FEE_BATCH_TIME.hour,
        MONTHLY_FEE_BATCH_TIME.minute,
        tzinfo=tz,
    )

    if now < this_month_first:
        target = this_month_first
    elif now.month == 12:
        target = datetime(
            now.year + 1,
            1,
            1,
            MONTHLY_FEE_BATCH_TIME.hour,
            MONTHLY_FEE_BATCH_TIME.minute,
            tzinfo=tz,
        )
    else:
        target = datetime(
            now.year,
            now.month + 1,
            1,
            MONTHLY_FEE_BATCH_TIME.hour,
            MONTHLY_FEE_BATCH_TIME.minute,
            tzinfo=tz,
        )

    return max((target - now).total_seconds(), 60.0)


def _prev_month_start(d: date) -> date:
    """指定日の前月月初を返す。"""
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _monthly_fee_batch_sync(calculation_month: date, usd_jpy_rate: Decimal) -> None:
    """月次手数料バッチの同期実行 (asyncio.to_thread から呼ばれる)。"""
    from sqlalchemy import select as _select  # noqa: PLC0415

    from app.api.v1.fees import finalize_month_core  # noqa: PLC0415
    from app.fees.billing_adapter import StubBillingAdapter  # noqa: PLC0415
    from app.fees.models import FeeConfigV10  # noqa: PLC0415

    with SessionLocal() as db:
        config = db.scalar(
            _select(FeeConfigV10)
            .where(FeeConfigV10.is_active.is_(True))
            .order_by(FeeConfigV10.effective_from.desc())
            .limit(1)
        )
        if config is None:
            logger.error(
                "monthly_fee_batch: active fee_config not found, skipping month=%s",
                calculation_month,
            )
            return
        vendor = StubBillingAdapter()
        result = finalize_month_core(
            db, config, calculation_month, usd_jpy_rate, vendor_adapter=vendor
        )
        logger.info(
            "monthly_fee_batch done: month=%s processed=%d skipped_no_snap=%d"
            " skipped_finalized=%d total_fee=%s vendor_charges=%d/%d",
            calculation_month,
            result.users_processed,
            result.users_skipped_no_snapshot,
            result.users_skipped_already_finalized,
            result.total_fee_jpy,
            result.vendor_charges_succeeded,
            result.vendor_charges_attempted,
        )


async def monthly_fee_batch_loop(
    *,
    usd_jpy_rate: Decimal = Decimal("150"),
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """月次手数料バッチ: 毎月1日 09:00 JST に前月分の fee_transactions を計算・登録する。

    ENABLE_MONTHLY_FEE_BATCH=1 で main.py から起動される。
    usd_jpy_rate は USD_TO_JPY_RATE 環境変数（デフォルト 150）を使う。
    """
    logger.info(
        "Starting monthly fee batch loop (schedule: 1st of month %s JST)", MONTHLY_FEE_BATCH_TIME
    )

    while True:
        try:
            wait_seconds = _calculate_seconds_until_month_first(tz=tz)
            logger.debug("Waiting %.1f seconds until next monthly fee batch", wait_seconds)
            await asyncio.sleep(wait_seconds)

            now_jst = datetime.now(tz)
            target_month = _prev_month_start(now_jst.date())

            logger.info("Running monthly fee batch for month=%s", target_month)
            await asyncio.to_thread(_monthly_fee_batch_sync, target_month, usd_jpy_rate)
            logger.info("Monthly fee batch completed for month=%s", target_month)

            await asyncio.sleep(3600)  # 重複実行防止

        except asyncio.CancelledError:
            logger.info("Monthly fee batch loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in monthly fee batch loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)
            await asyncio.sleep(3600)


def _extract_line_user_id(email: str) -> Optional[str]:
    """LINE 認証ユーザーのメールアドレスから LINE user_id を抽出する。

    LINE 認証ユーザーのメールは line_{user_id}@line.local 形式。
    """
    prefix = "line_"
    suffix = "@line.local"
    if email.startswith(prefix) and email.endswith(suffix):
        return email[len(prefix) : -len(suffix)]
    return None


def _monthly_line_report_sync(calculation_month: date, channel_access_token: str) -> int:
    """月次 LINE レポートを送信する同期関数 (asyncio.to_thread から呼ばれる)。

    line_monthly_opt_in=True かつ LINE 認証済み (email=line_*@line.local) の
    ユーザーに Flex Message を一括送信する。

    Returns:
        送信成功ユーザー数
    """

    from decimal import Decimal as _Decimal  # noqa: PLC0415

    from sqlalchemy import func, select  # noqa: PLC0415

    from app.auth.models import User  # noqa: PLC0415
    from app.fees.models import FeeTransaction  # noqa: PLC0415
    from app.notifications.line_messaging import (  # noqa: PLC0415
        LINEFlexMessageSender,
        build_monthly_report_flex_bubble,
    )
    from app.proposals.models import Proposal  # noqa: PLC0415

    period_str = f"{calculation_month.year}年{calculation_month.month}月"

    with SessionLocal() as db:
        # opt-in かつ LINE 認証済みユーザーを抽出
        opted_in_users = (
            db.query(User)
            .filter(
                User.line_monthly_opt_in.is_(True),
                User.email.like("line_%@line.local"),
                User.is_active.is_(True),
            )
            .all()
        )

        if not opted_in_users:
            logger.info(
                "monthly_line_report: no opted-in LINE users for month=%s", calculation_month
            )
            return 0

        sent_count = 0
        for user in opted_in_users:
            line_user_id = _extract_line_user_id(user.email)
            if not line_user_id:
                continue

            # ユーザー個別の月次データを集計
            fee_row = db.execute(
                select(
                    func.sum(FeeTransaction.net_profit_jpy).label("net_profit"),
                    func.sum(FeeTransaction.fee_amount_jpy).label("fee_amount"),
                ).where(
                    FeeTransaction.user_id == user.id,
                    FeeTransaction.calculation_month == calculation_month,
                )
            ).one()

            net_profit = fee_row.net_profit or _Decimal("0")
            fee_amount = fee_row.fee_amount or _Decimal("0")

            # 提案・勝率集計
            month_start = calculation_month
            if month_start.month == 12:
                month_end = date(month_start.year + 1, 1, 1)
            else:
                month_end = date(month_start.year, month_start.month + 1, 1)

            total_proposals = (
                db.query(func.count(Proposal.id))
                .filter(
                    Proposal.user_id == user.id,
                    Proposal.created_at >= month_start,
                    Proposal.created_at < month_end,
                )
                .scalar()
                or 0
            )
            executed_count = (
                db.query(func.count(Proposal.id))
                .filter(
                    Proposal.user_id == user.id,
                    Proposal.created_at >= month_start,
                    Proposal.created_at < month_end,
                    Proposal.status == "executed",
                )
                .scalar()
                or 0
            )
            win_rate = (executed_count / total_proposals * 100.0) if total_proposals > 0 else 0.0

            flex_msg = build_monthly_report_flex_bubble(
                period=period_str,
                net_profit_jpy=net_profit,
                fee_amount_jpy=fee_amount,
                win_rate=win_rate,
                total_proposals=total_proposals,
            )

            sender = LINEFlexMessageSender(
                channel_access_token=channel_access_token,
                user_id=line_user_id,
            )
            if sender.push_flex_message(flex_msg):
                sent_count += 1
                logger.info(
                    "monthly_line_report sent: user_id=%d, month=%s",
                    user.id,
                    calculation_month,
                )
            else:
                logger.warning(
                    "monthly_line_report send failed: user_id=%d, month=%s",
                    user.id,
                    calculation_month,
                )

        logger.info(
            "monthly_line_report done: month=%s sent=%d/%d",
            calculation_month,
            sent_count,
            len(opted_in_users),
        )
        return sent_count


async def monthly_line_report_loop(
    *,
    tz: ZoneInfo = DEFAULT_TIMEZONE,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """月次 LINE レポート送信ループ: 毎月1日 10:00 JST に実行。

    ENABLE_MONTHLY_LINE_REPORT=1 かつ LINE_CHANNEL_ACCESS_TOKEN 設定時に
    main.py から起動される。月次手数料バッチ (09:00 JST) 完了後の
    10:00 JST に、opt-in 済み一般ユーザーへ Flex Message を一括送信する。
    """
    import os  # noqa: PLC0415

    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not channel_access_token:
        logger.warning(
            "monthly_line_report_loop: LINE_CHANNEL_ACCESS_TOKEN not set, loop will not send"
        )

    logger.info(
        "Starting monthly LINE report loop (schedule: 1st of month %s JST)",
        MONTHLY_LINE_REPORT_TIME,
    )

    while True:
        try:
            wait_seconds = _calculate_seconds_until_month_first(tz=tz)
            # fee_batch は 09:00、LINE レポートは 10:00 → 3600 秒ずらす
            wait_seconds = max(wait_seconds + 3600, 60.0)
            logger.debug(
                "Waiting %.1f seconds until next monthly LINE report",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

            if not channel_access_token:
                logger.warning(
                    "monthly_line_report_loop: skipping (LINE_CHANNEL_ACCESS_TOKEN not set)"
                )
                await asyncio.sleep(3600)
                continue

            now_jst = datetime.now(tz)
            target_month = _prev_month_start(now_jst.date())

            logger.info("Running monthly LINE report for month=%s", target_month)
            await asyncio.to_thread(
                _monthly_line_report_sync,
                target_month,
                channel_access_token,
            )

            await asyncio.sleep(3600)  # 重複実行防止

        except asyncio.CancelledError:
            logger.info("Monthly LINE report loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in monthly LINE report loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)
            await asyncio.sleep(3600)


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


async def proposal_expiry_reminder_loop(
    *,
    interval_seconds: int = 300,
    reminder_before_minutes: int = 30,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    期限切れ前 Proposal に対してリマインダー通知を送る定期ループ。

    ``reminder_before_minutes`` 分以内に期限切れを迎える pending かつ
    まだ通知未送信 (expiry_reminder_sent_at is None) の Proposal を検出し、
    LINE 通知を送信後 expiry_reminder_sent_at を更新する。

    Args:
        interval_seconds: チェック間隔（秒）。デフォルト 300 秒（5 分）
        reminder_before_minutes: 期限の何分前から通知するか。デフォルト 30 分
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting proposal expiry reminder loop (interval: %ds, window: %dmin)",
        interval_seconds,
        reminder_before_minutes,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            def _run_expiry_reminder() -> None:
                from datetime import datetime, timedelta, timezone  # noqa: PLC0415

                from app.database import SessionLocal  # noqa: PLC0415

                db = SessionLocal()
                try:
                    from app.notifications.factory import get_notification_service  # noqa: PLC0415
                    from app.notifications.templates import (  # noqa: PLC0415
                        expiry_reminder_notification,
                    )
                    from app.proposals.models import Proposal  # noqa: PLC0415

                    now = datetime.now(timezone.utc)
                    window_end = now + timedelta(minutes=reminder_before_minutes)

                    candidates = (
                        db.query(Proposal)
                        .filter(
                            Proposal.status == "pending",
                            Proposal.expires_at <= window_end,
                            Proposal.expires_at > now,
                            Proposal.expiry_reminder_sent_at.is_(None),
                        )
                        .all()
                    )

                    notified_count = 0
                    for proposal in candidates:
                        try:
                            minutes_left = max(
                                1,
                                int((proposal.expires_at - now).total_seconds() // 60),
                            )
                            payload = expiry_reminder_notification(
                                operation=proposal.operation,
                                asset=proposal.asset,
                                minutes_remaining=minutes_left,
                            )
                            msg = payload.notification_message
                            msg = msg.model_copy(update={"user_id": proposal.user_id})

                            try:
                                svc = get_notification_service()
                                svc.send(msg)
                            except Exception as _svc_exc:
                                logger.debug(
                                    "Expiry reminder notification failed for proposal %d: %s",
                                    proposal.id,
                                    _svc_exc,
                                )

                            proposal.expiry_reminder_sent_at = now
                            db.flush()
                            notified_count += 1
                            logger.info(
                                "Expiry reminder sent for proposal %d (op=%s, asset=%s, %dmin left)",
                                proposal.id,
                                proposal.operation,
                                proposal.asset,
                                minutes_left,
                            )
                        except Exception as _item_exc:
                            logger.warning(
                                "Failed to process expiry reminder for proposal %d: %s",
                                proposal.id,
                                _item_exc,
                            )

                    if notified_count:
                        db.commit()
                        logger.info("Expiry reminders sent for %d proposals", notified_count)

                except Exception as _db_exc:
                    db.rollback()
                    logger.warning("Proposal expiry reminder check DB error: %s", _db_exc)
                finally:
                    db.close()

            await asyncio.to_thread(_run_expiry_reminder)

        except asyncio.CancelledError:
            logger.info("Proposal expiry reminder loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in proposal expiry reminder loop: %s", exc)
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

            # 多層防御の第3層: ループが何らかの経路で起動していても、フラグ未設定なら
            # POST せずスキップ（runtime トグル・別経路起動への保険）。2026-06 CEX 裏線封鎖。
            if os.getenv("NEWS_AUTO_EXECUTE_ENABLED", "false").lower() not in ("true", "1", "yes"):
                logger.info("process_news_loop: NEWS_AUTO_EXECUTE_ENABLED not set, skipping POST")
                continue

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
                    params={"dry_run": "false"},
                    headers={"X-Internal-Token": token},
                    timeout=120.0,
                )
                resp.raise_for_status()  # 4xx/5xx を HTTPStatusError として伝播

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


async def outcome_labeling_loop(
    *,
    interval_seconds: int = 21600,  # 6 時間
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Layer 2 outcome label 収集バッチの定期実行ループ。

    6 時間ごとに OutcomeLabelingService.run_batch() を実行し、
    AI判定から 24h / 48h 後の realized_yield_delta / hf_min_after /
    regret_score / is_positive_example を ai_decision_outcomes に INSERT する。

    ENABLE_OUTCOME_LABELING=1 で main.py から起動される。
    """
    logger.info(
        "Starting outcome labeling loop (interval: %ds)",
        interval_seconds,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            logger.info("Running outcome labeling batch")

            def _run_labeling() -> None:
                from app.ai.outcome_labeling_service import OutcomeLabelingService  # noqa: PLC0415

                with SessionLocal() as db:
                    svc = OutcomeLabelingService(db)
                    result = svc.run_batch()
                    logger.info(
                        "outcome_labeling_batch done: processed=%d errors=%d completed_at=%s",
                        result.total_processed,
                        result.total_errors,
                        result.completed_at,
                    )

            await asyncio.to_thread(_run_labeling)
            logger.info("Outcome labeling batch completed")

        except asyncio.CancelledError:
            logger.info("Outcome labeling loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in outcome labeling loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


async def compound_risk_monitor_loop(
    *,
    interval_seconds: int = COMPOUND_RISK_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """複合リスク評価（CompoundRiskAssessor）と自動避難計画（AutoEvacuator）の定期実行ループ。

    10 分ごとに全プロトコルの複合リスクを評価し、
    should_evacuate が True の場合は避難計画を dry_run で作成・ログ出力する。

    Args:
        interval_seconds: チェック間隔（秒）。デフォルト 600 秒（10 分）
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-open）
    """
    from app.protocols.risk.auto_evacuate import AutoEvacuator  # noqa: PLC0415
    from app.protocols.risk.compound_risk import CompoundRiskAssessor  # noqa: PLC0415

    logger.info(
        "Starting compound risk monitor loop (interval: %ds)",
        interval_seconds,
    )

    assessor = CompoundRiskAssessor()
    evacuator = AutoEvacuator()

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            logger.info("compound_risk_monitor_loop: 複合リスク評価開始")
            assessment = await assessor.assess()
            logger.info(
                "compound_risk_monitor_loop: overall_risk=%s, score=%s, should_evacuate=%s",
                assessment.overall_risk.value,
                assessment.risk_score,
                assessment.should_evacuate,
            )

            if assessment.should_evacuate:
                logger.warning(
                    "compound_risk_monitor_loop: 避難条件成立 — 避難計画を作成します (reason=%s)",
                    assessment.evacuation_reason,
                )
                plan = await evacuator.create_evacuation_plan(assessment)
                if plan is not None:
                    result = await evacuator.execute_evacuation(plan, dry_run=True)
                    logger.warning(
                        "compound_risk_monitor_loop: 避難計画 dry_run 完了 "
                        "(steps=%d/%d, priority=%s)",
                        result.steps_completed,
                        result.steps_total,
                        plan.priority,
                    )

        except asyncio.CancelledError:
            logger.info("compound_risk_monitor_loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in compound risk monitor loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


def _parse_oracle_monitor_feeds(raw: str) -> list["OracleFeedConfig"]:
    """``ORACLE_MONITOR_FEEDS``(JSON) を解析する。

    形式: ``[{"name":"USDC","feed_address":"0x...","rpc_url":"https://..."}, ...]``。
    不正 JSON / 非 list / キー欠落は fail-safe（[] / 該当エントリ skip）。
    """
    from app.automation.oracle_monitor import OracleFeedConfig  # noqa: PLC0415

    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("ORACLE_MONITOR_FEEDS is not valid JSON — oracle monitor has no feeds")
        return []
    if not isinstance(items, list):
        logger.warning("ORACLE_MONITOR_FEEDS must be a JSON array — oracle monitor has no feeds")
        return []
    feeds: list[OracleFeedConfig] = []
    for it in items:
        try:
            feeds.append(
                OracleFeedConfig(
                    name=str(it["name"]),
                    feed_address=str(it["feed_address"]),
                    rpc_url=str(it["rpc_url"]),
                )
            )
        except (KeyError, TypeError):
            logger.warning("ORACLE_MONITOR_FEEDS entry missing name/feed_address/rpc_url — skipped")
    return feeds


def _feeds_from_aave_oracle_assets(raw: str) -> list["OracleFeedConfig"]:
    """既存 ``AAVE_ORACLE_ASSETS_JSON``（oracle_checker と共有の真実源）から feed を導出する。

    形式: ``[{"asset":"USDC","chainlink_feed":"0x...","rpc_url":"https://...", ...}, ...]``。
    ``chainlink_feed`` と ``rpc_url`` が揃うエントリのみ採用（無いものは monitor 対象外）。
    監視と per-tx HARD_STOP で feed アドレスを二重管理しないための単一ソース化（drift 防止）。
    """
    from app.automation.oracle_monitor import OracleFeedConfig  # noqa: PLC0415

    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    feeds: list[OracleFeedConfig] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        feed_addr = it.get("chainlink_feed")
        rpc_url = it.get("rpc_url")
        asset = it.get("asset")
        if feed_addr and rpc_url and asset:
            feeds.append(
                OracleFeedConfig(name=str(asset), feed_address=str(feed_addr), rpc_url=str(rpc_url))
            )
    return feeds


def _build_oracle_feeds_from_env() -> list["OracleFeedConfig"]:
    """監視フィード設定を構築する（fail-safe で [] を返し起動を妨げない）。

    解決順:
      1. ``ORACLE_MONITOR_FEEDS``（明示指定・monitor 専用上書き）
      2. ``AAVE_ORACLE_ASSETS_JSON``（既存 oracle_checker と共有・**単一ソース推奨**）

    feed アドレスを 2 箇所で二重管理しないため、通常は既存 ``AAVE_ORACLE_ASSETS_JSON`` を
    そのまま再利用し、ON は ``ENABLE_ORACLE_MONITOR=1`` だけで済むようにする。
    """
    explicit = os.getenv("ORACLE_MONITOR_FEEDS", "").strip()
    if explicit:
        return _parse_oracle_monitor_feeds(explicit)
    shared = os.getenv("AAVE_ORACLE_ASSETS_JSON", "").strip()
    if shared:
        feeds = _feeds_from_aave_oracle_assets(shared)
        if feeds:
            logger.info(
                "oracle monitor feeds derived from AAVE_ORACLE_ASSETS_JSON (%d feeds)", len(feeds)
            )
        return feeds
    return []


async def oracle_monitor_loop(
    *,
    interval_seconds: int = ORACLE_MONITOR_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Chainlink oracle の staleness / 価格乖離を定期ポーリングし、異常時に
    ``MonitoringService.activate_emergency_stop`` を発火するループ（OracleMonitor 配線）。

    ``ORACLE_MONITOR_FEEDS`` 未設定（=フィードゼロ）なら起動せず即終了する（dormant）。
    発火条件は OracleMonitor 既定（oracle 異常 AND HF<1.8、または極端異常で fail-safe）。
    check_once() は同期（web3 RPC）なので executor で実行しイベントループを塞がない。
    """
    from app.automation.oracle_monitor import OracleMonitor  # noqa: PLC0415
    from app.automation.state import get_monitoring_service  # noqa: PLC0415

    feeds = _build_oracle_feeds_from_env()
    if not feeds:
        logger.warning(
            "oracle_monitor_loop: no feeds configured (ORACLE_MONITOR_FEEDS) — not starting"
        )
        return

    monitor = OracleMonitor(get_monitoring_service(), feeds)
    logger.info(
        "Starting oracle monitor loop (interval: %ds, feeds: %d)", interval_seconds, len(feeds)
    )
    loop = asyncio.get_running_loop()

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            report = await loop.run_in_executor(None, monitor.check_once)
            logger.info(
                "oracle_monitor_loop: anomaly=%s, emergency=%s, fetch_failures=%d",
                report.anomaly_detected,
                report.emergency_triggered,
                len(report.fetch_failures),
            )
            if report.emergency_triggered:
                logger.warning(
                    "oracle_monitor_loop: emergency_stop fired (reasons=%s)",
                    "; ".join(report.reasons),
                )

        except asyncio.CancelledError:
            logger.info("oracle_monitor_loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in oracle monitor loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(interval_seconds)


async def pool_health_check_loop(
    *,
    interval_seconds: int = POOL_HEALTH_CHECK_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    Aave プール赤字（getReserveDeficit）を定期監視するバックグラウンドループ。

    interval_seconds ごとに PoolHealthMonitor.check_pool_deficits() を呼び出し、
    赤字が DEFICIT_ALERT_THRESHOLD ($10,000) を超えた場合は Slack アラートを発火する。

    起動方法:
        ScheduledTaskManager.start_pool_health_check() 経由で呼び出す。
        直接呼び出しは禁止（二重起動防止のためマネージャ経由にすること）。

    本番への配線（main.py lifespan）は ENABLE_POOL_HEALTH_MONITOR=1 設定後に
    別途 human 承認 PR で追加すること。

    現在の監視対象: USDC のみ。
    WETH / wstETH は Aave Price Oracle 統合後に追加する（MAJOR #1 参照）。
    """
    logger.info("pool_health_check_loop started (interval=%ds)", interval_seconds)

    while True:
        try:
            import os  # noqa: PLC0415

            from app.aave.liquidation_sentinel import PoolHealthMonitor  # noqa: PLC0415

            chain_name = os.getenv("AAVE_ACTIVE_CHAINS", "base").split(",")[0].strip()
            monitor = PoolHealthMonitor()
            report = monitor.check_pool_deficits(chain_name=chain_name)

            if report.alert_triggered:
                logger.warning(
                    "pool_health_check_loop: アラート発火 chain=%s total_deficit=%s",
                    chain_name,
                    report.total_deficit_usd,
                )
            else:
                logger.info(
                    "pool_health_check_loop: チェック完了 chain=%s total_deficit=%s",
                    chain_name,
                    report.total_deficit_usd,
                )

        except asyncio.CancelledError:
            logger.info("pool_health_check_loop cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("pool_health_check_loop エラー: %s", exc, exc_info=True)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

        await asyncio.sleep(interval_seconds)


async def reward_auto_claim_loop(
    *,
    interval_seconds: int = REWARD_AUTO_CLAIM_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    Aave リワード自動 Claim + 複利再投資の定期実行ループ。

    毎日 03:00 UTC に RewardClaimer.auto_claim_if_worthy() を実行する。

    NOTE: main.py への startup 配線は HUMAN-REVIEW-REQUIRED (Tier S 別 PR 必須)。
    有効化手順は ScheduledTaskManager.start_reward_auto_claim() のコードブロックを参照。

    AAVE_UI_INCENTIVE_PROVIDER_ADDRESS / AAVE_REWARDS_CONTROLLER_ADDRESS /
    AAVE_POOL_ADDRESSES_PROVIDER が未設定の場合は warn ログのみで継続 (fail-open)。

    Args:
        interval_seconds: 実行間隔（秒）。デフォルト 86400 秒（24 時間）
        on_error: エラー発生時のコールバック
    """
    import os  # noqa: PLC0415

    logger.info(
        "Starting reward auto-claim loop (interval: %ds, target: %02d:00 UTC)",
        interval_seconds,
        REWARD_AUTO_CLAIM_UTC_HOUR,
    )

    while True:
        try:
            # UTC 03:00 まで待機する（_calculate_seconds_until は JST ベースのため UTC 換算）
            from datetime import time as _time  # noqa: PLC0415
            from zoneinfo import ZoneInfo as _ZoneInfo  # noqa: PLC0415

            utc_target = _time(REWARD_AUTO_CLAIM_UTC_HOUR, 0)
            wait_seconds = _calculate_seconds_until(utc_target, tz=_ZoneInfo("UTC"))
            logger.debug("reward_auto_claim_loop: waiting %.1f seconds", wait_seconds)
            await asyncio.sleep(wait_seconds)

            logger.info("reward_auto_claim_loop: Aave リワード Claim 開始")

            def _run_claim() -> dict[str, object]:
                from app.aave.reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

                claimer = make_reward_claimer_from_env()
                if claimer is None:
                    logger.warning(
                        "reward_auto_claim_loop: RewardClaimer が生成できません "
                        "(env 未設定) — スキップ"
                    )
                    return {"claimed": False, "skip_reason": "claimer unavailable"}

                wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")
                private_key = os.getenv("AAVE_WALLET_PRIVATE_KEY", "")

                if not wallet_address or not private_key:
                    logger.warning(
                        "reward_auto_claim_loop: AAVE_WALLET_ADDRESS or "
                        "AAVE_WALLET_PRIVATE_KEY not set — スキップ"
                    )
                    return {"claimed": False, "skip_reason": "wallet/key not set"}

                return claimer.auto_claim_if_worthy(
                    wallet_address=wallet_address,
                    private_key=private_key,
                    dry_run=False,
                )

            result = await asyncio.to_thread(_run_claim)
            logger.info(
                "reward_auto_claim_loop 完了: claimed=%s, total_usd=%s, skip=%s, error=%s",
                result.get("claimed"),
                result.get("total_usd"),
                result.get("skip_reason"),
                result.get("error"),
            )

            # 重複実行防止
            await asyncio.sleep(3600)

        except asyncio.CancelledError:
            logger.info("reward_auto_claim_loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in reward auto-claim loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            await asyncio.sleep(600)


# アイドル資本チェックループのデフォルト間隔 (ScheduledTaskManager が参照)
IDLE_CAPITAL_CHECK_INTERVAL_SECONDS = 900  # 15 分


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
        self._outcome_labeling_task: Optional[asyncio.Task[None]] = None
        self._compound_risk_task: Optional[asyncio.Task[None]] = None
        self._oracle_monitor_task: Optional[asyncio.Task[None]] = None
        self._monthly_fee_batch_task: Optional[asyncio.Task[None]] = None
        self._monthly_line_report_task: Optional[asyncio.Task[None]] = None
        self._expiry_reminder_task: Optional[asyncio.Task[None]] = None
        # プール赤字監視タスク（MAJOR #3: LiquidationSentinel）
        # 起動は main.py への startup 配線で行う（別途 human 承認 PR が必要）。
        # env フラグ ENABLE_POOL_HEALTH_MONITOR=1 でのみ有効化すること。
        # 二重起動を防ぐために is_pool_health_check_running を確認してから start を呼ぶこと。
        self._pool_health_check_task: Optional[asyncio.Task[None]] = None
        self._reward_auto_claim_task: Optional[asyncio.Task[None]] = None
        self._idle_capital_check_task: Optional[asyncio.Task[None]] = None

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

    @property
    def is_outcome_labeling_running(self) -> bool:
        """outcome label 収集タスクが動作中かどうか。"""
        return self._outcome_labeling_task is not None and not self._outcome_labeling_task.done()

    @property
    def is_compound_risk_running(self) -> bool:
        """複合リスク監視タスクが動作中かどうか。"""
        return self._compound_risk_task is not None and not self._compound_risk_task.done()

    @property
    def is_oracle_monitor_running(self) -> bool:
        """oracle 監視タスクが動作中かどうか。"""
        return self._oracle_monitor_task is not None and not self._oracle_monitor_task.done()

    @property
    def is_monthly_fee_batch_running(self) -> bool:
        """月次手数料バッチタスクが動作中かどうか。"""
        return self._monthly_fee_batch_task is not None and not self._monthly_fee_batch_task.done()

    @property
    def is_monthly_line_report_running(self) -> bool:
        """月次 LINE レポートタスクが動作中かどうか。"""
        return (
            self._monthly_line_report_task is not None and not self._monthly_line_report_task.done()
        )

    @property
    def is_expiry_reminder_running(self) -> bool:
        """期限切れリマインダータスクが動作中かどうか。"""
        return self._expiry_reminder_task is not None and not self._expiry_reminder_task.done()

    @property
    def is_pool_health_check_running(self) -> bool:
        """プール赤字監視タスクが動作中かどうか。"""
        return self._pool_health_check_task is not None and not self._pool_health_check_task.done()

    @property
    def is_reward_auto_claim_running(self) -> bool:
        """リワード自動 Claim タスクが動作中かどうか。"""
        return self._reward_auto_claim_task is not None and not self._reward_auto_claim_task.done()

    @property
    def is_idle_capital_check_running(self) -> bool:
        """アイドル資本チェックタスクが動作中かどうか。"""
        return (
            self._idle_capital_check_task is not None and not self._idle_capital_check_task.done()
        )

    async def start_monthly_line_report(
        self,
        *,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """月次 LINE レポートタスクを開始する。"""
        if self.is_monthly_line_report_running:
            raise RuntimeError("Monthly LINE report already running")

        logger.info("Starting monthly LINE report task")
        self._monthly_line_report_task = asyncio.create_task(
            monthly_line_report_loop(on_error=on_error)
        )
        logger.info("Monthly LINE report task started")

    async def stop_monthly_line_report(self, timeout: float = 5.0) -> None:
        """月次 LINE レポートタスクを停止する。"""
        if not self.is_monthly_line_report_running:
            logger.debug("Monthly LINE report not running - nothing to stop")
            return

        logger.info("Stopping monthly LINE report task")
        assert self._monthly_line_report_task is not None  # noqa: S101
        self._monthly_line_report_task.cancel()

        try:
            await asyncio.wait_for(self._monthly_line_report_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Monthly LINE report task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Monthly LINE report task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping monthly LINE report task: %s", exc)

        self._monthly_line_report_task = None
        logger.info("Monthly LINE report task stopped")

    async def start_monthly_fee_batch(
        self,
        *,
        usd_jpy_rate: Decimal = Decimal("150"),
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """月次手数料バッチタスクを開始する。"""
        if self.is_monthly_fee_batch_running:
            raise RuntimeError("Monthly fee batch already running")

        logger.info("Starting monthly fee batch task (rate=%s)", usd_jpy_rate)
        self._monthly_fee_batch_task = asyncio.create_task(
            monthly_fee_batch_loop(usd_jpy_rate=usd_jpy_rate, on_error=on_error)
        )
        logger.info("Monthly fee batch task started")

    async def stop_monthly_fee_batch(self, timeout: float = 5.0) -> None:
        """月次手数料バッチタスクを停止する。"""
        if not self.is_monthly_fee_batch_running:
            logger.debug("Monthly fee batch not running - nothing to stop")
            return

        logger.info("Stopping monthly fee batch task")
        assert self._monthly_fee_batch_task is not None  # noqa: S101
        self._monthly_fee_batch_task.cancel()

        try:
            await asyncio.wait_for(self._monthly_fee_batch_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Monthly fee batch task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Monthly fee batch task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping monthly fee batch task: %s", exc)

        self._monthly_fee_batch_task = None
        logger.info("Monthly fee batch task stopped")

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

    async def start_outcome_labeling(
        self,
        *,
        interval_seconds: int = 21600,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """outcome label 収集タスクを開始する。"""
        if self.is_outcome_labeling_running:
            raise RuntimeError("Outcome labeling already running")

        logger.info("Starting outcome labeling task")
        self._outcome_labeling_task = asyncio.create_task(
            outcome_labeling_loop(interval_seconds=interval_seconds, on_error=on_error)
        )
        logger.info("Outcome labeling task started")

    async def stop_outcome_labeling(self, timeout: float = 5.0) -> None:
        """outcome label 収集タスクを停止する。"""
        if not self.is_outcome_labeling_running:
            logger.debug("Outcome labeling not running - nothing to stop")
            return

        logger.info("Stopping outcome labeling task")
        assert self._outcome_labeling_task is not None  # noqa: S101
        self._outcome_labeling_task.cancel()

        try:
            await asyncio.wait_for(self._outcome_labeling_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Outcome labeling task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Outcome labeling task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping outcome labeling task: %s", exc)

        self._outcome_labeling_task = None
        logger.info("Outcome labeling task stopped")

    async def start_compound_risk_monitor(
        self,
        *,
        interval_seconds: int = COMPOUND_RISK_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """複合リスク監視タスクを開始する。

        Args:
            interval_seconds: チェック間隔（秒）
            on_error: エラー時コールバック

        Raises:
            RuntimeError: 既に開始されている場合
        """
        if self.is_compound_risk_running:
            raise RuntimeError("Compound risk monitor already running")

        logger.info("Starting compound risk monitor task")

        self._compound_risk_task = asyncio.create_task(
            compound_risk_monitor_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )

        logger.info("Compound risk monitor task started")

    async def stop_compound_risk_monitor(self, timeout: float = 5.0) -> None:
        """複合リスク監視タスクを停止する。

        Args:
            timeout: キャンセル待機のタイムアウト秒数
        """
        if not self.is_compound_risk_running:
            logger.debug("Compound risk monitor not running - nothing to stop")
            return

        logger.info("Stopping compound risk monitor task")

        assert self._compound_risk_task is not None  # noqa: S101
        self._compound_risk_task.cancel()

        try:
            await asyncio.wait_for(self._compound_risk_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Compound risk monitor task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Compound risk monitor task did not stop within %.1fs timeout",
                timeout,
            )
        except Exception as exc:
            logger.error("Error while stopping compound risk monitor task: %s", exc)

        self._compound_risk_task = None
        logger.info("Compound risk monitor task stopped")

    async def start_oracle_monitor(
        self,
        *,
        interval_seconds: int = ORACLE_MONITOR_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """oracle 監視タスクを開始する（フィード未設定なら即終了する dormant ループ）。

        Raises:
            RuntimeError: 既に開始されている場合
        """
        if self.is_oracle_monitor_running:
            raise RuntimeError("Oracle monitor already running")

        logger.info("Starting oracle monitor task")
        self._oracle_monitor_task = asyncio.create_task(
            oracle_monitor_loop(interval_seconds=interval_seconds, on_error=on_error)
        )
        logger.info("Oracle monitor task started")

    async def stop_oracle_monitor(self, timeout: float = 5.0) -> None:
        """oracle 監視タスクを停止する。"""
        if not self.is_oracle_monitor_running:
            logger.debug("Oracle monitor not running - nothing to stop")
            return

        logger.info("Stopping oracle monitor task")
        assert self._oracle_monitor_task is not None  # noqa: S101
        self._oracle_monitor_task.cancel()

        try:
            await asyncio.wait_for(self._oracle_monitor_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Oracle monitor task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Oracle monitor task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping oracle monitor task: %s", exc)

        self._oracle_monitor_task = None
        logger.info("Oracle monitor task stopped")

    async def start_expiry_reminder(
        self,
        *,
        interval_seconds: int = 300,
        reminder_before_minutes: int = 30,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """期限切れリマインダータスクを開始する。"""
        if self.is_expiry_reminder_running:
            raise RuntimeError("Expiry reminder already running")

        logger.info("Starting proposal expiry reminder task")
        self._expiry_reminder_task = asyncio.create_task(
            proposal_expiry_reminder_loop(
                interval_seconds=interval_seconds,
                reminder_before_minutes=reminder_before_minutes,
                on_error=on_error,
            )
        )
        logger.info("Proposal expiry reminder task started")

    async def stop_expiry_reminder(self, timeout: float = 5.0) -> None:
        """期限切れリマインダータスクを停止する。"""
        if not self.is_expiry_reminder_running:
            logger.debug("Expiry reminder not running - nothing to stop")
            return

        logger.info("Stopping proposal expiry reminder task")
        assert self._expiry_reminder_task is not None  # noqa: S101
        self._expiry_reminder_task.cancel()

        try:
            await asyncio.wait_for(self._expiry_reminder_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Proposal expiry reminder task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Proposal expiry reminder task did not stop within %.1fs timeout", timeout
            )
        except Exception as exc:
            logger.error("Error while stopping proposal expiry reminder task: %s", exc)

        self._expiry_reminder_task = None
        logger.info("Proposal expiry reminder task stopped")

    async def start_pool_health_check(
        self,
        *,
        interval_seconds: int = POOL_HEALTH_CHECK_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        プール赤字監視タスクを開始する。

        Aave Pool.getReserveDeficit() を定期実行し、赤字が $10,000 を超えた場合に
        Slack アラートを発火する。

        IMPORTANT: このメソッドは main.py の lifespan からは呼ばれない。
        起動するには以下の手順が必要:
          1. ENABLE_POOL_HEALTH_MONITOR=1 を .env に設定する
          2. 別途 human 承認 PR で main.py/lifespan に以下を追加する:
               import os
               if os.getenv("ENABLE_POOL_HEALTH_MONITOR") == "1":
                   await manager.start_pool_health_check()
          3. 二重起動防止のために is_pool_health_check_running を確認してから呼ぶこと。

        現在の監視対象: USDC のみ（WETH/wstETH は Price Oracle 統合後に追加予定）。
        """
        if self.is_pool_health_check_running:
            logger.warning(
                "Pool health check task already running — double-start prevented. "
                "Check ENABLE_POOL_HEALTH_MONITOR env flag and lifespan wiring."
            )
            return

        logger.info("Starting pool health check task (interval=%ds)", interval_seconds)
        self._pool_health_check_task = asyncio.create_task(
            pool_health_check_loop(
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        )
        logger.info("Pool health check task started")

    async def stop_pool_health_check(self, timeout: float = 5.0) -> None:
        """プール赤字監視タスクを停止する。"""
        if not self.is_pool_health_check_running:
            logger.debug("Pool health check not running - nothing to stop")
            return

        logger.info("Stopping pool health check task")
        assert self._pool_health_check_task is not None  # noqa: S101
        self._pool_health_check_task.cancel()

        try:
            await asyncio.wait_for(self._pool_health_check_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Pool health check task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Pool health check task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping pool health check task: %s", exc)

        self._pool_health_check_task = None
        logger.info("Pool health check task stopped")

    async def start_reward_auto_claim(
        self,
        *,
        interval_seconds: int = REWARD_AUTO_CLAIM_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """リワード自動 Claim タスクを開始する。"""
        if self.is_reward_auto_claim_running:
            raise RuntimeError("Reward auto-claim already running")

        logger.info("Starting reward auto-claim task")
        self._reward_auto_claim_task = asyncio.create_task(
            reward_auto_claim_loop(interval_seconds=interval_seconds, on_error=on_error)
        )
        logger.info("Reward auto-claim task started")

    async def stop_reward_auto_claim(self, timeout: float = 5.0) -> None:
        """リワード自動 Claim タスクを停止する。"""
        if not self.is_reward_auto_claim_running:
            logger.debug("Reward auto-claim not running - nothing to stop")
            return

        logger.info("Stopping reward auto-claim task")
        assert self._reward_auto_claim_task is not None  # noqa: S101
        self._reward_auto_claim_task.cancel()

        try:
            await asyncio.wait_for(self._reward_auto_claim_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Reward auto-claim task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Reward auto-claim task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping reward auto-claim task: %s", exc)

        self._reward_auto_claim_task = None
        logger.info("Reward auto-claim task stopped")

    async def start_idle_capital_check(
        self,
        *,
        interval_seconds: int = IDLE_CAPITAL_CHECK_INTERVAL_SECONDS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """アイドル資本チェックタスクを開始する (ENABLE_IDLE_CAPITAL_CHECK=1)。"""
        if self.is_idle_capital_check_running:
            raise RuntimeError("Idle capital check already running")

        logger.info("Starting idle capital check task")
        self._idle_capital_check_task = asyncio.create_task(
            idle_capital_check_loop(interval_seconds=interval_seconds, on_error=on_error)
        )
        logger.info("Idle capital check task started")

    async def stop_idle_capital_check(self, timeout: float = 5.0) -> None:
        """アイドル資本チェックタスクを停止する。"""
        if not self.is_idle_capital_check_running:
            logger.debug("Idle capital check not running - nothing to stop")
            return

        logger.info("Stopping idle capital check task")
        assert self._idle_capital_check_task is not None  # noqa: S101
        self._idle_capital_check_task.cancel()

        try:
            await asyncio.wait_for(self._idle_capital_check_task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Idle capital check task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning("Idle capital check task did not stop within %.1fs timeout", timeout)
        except Exception as exc:
            logger.error("Error while stopping idle capital check task: %s", exc)

        self._idle_capital_check_task = None
        logger.info("Idle capital check task stopped")

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
            self.stop_outcome_labeling(timeout=timeout),
            self.stop_compound_risk_monitor(timeout=timeout),
            self.stop_monthly_fee_batch(timeout=timeout),
            self.stop_monthly_line_report(timeout=timeout),
            self.stop_expiry_reminder(timeout=timeout),
            self.stop_pool_health_check(timeout=timeout),
            self.stop_reward_auto_claim(timeout=timeout),
            self.stop_idle_capital_check(timeout=timeout),
            return_exceptions=True,
        )

        logger.info("All scheduled tasks stopped")


# ---- idle_capital_check_loop (Privy Earn / Morpho Vaults アイドル資本チェック) ----


async def idle_capital_check_loop(
    *,
    interval_seconds: int = IDLE_CAPITAL_CHECK_INTERVAL_SECONDS,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    アイドル資本チェックの定期実行ループ。

    15 分ごとに IdleCapitalDetector.build_report() を実行し、
    デプロイ推奨時は INFO ログを出力する。
    ENABLE_IDLE_CAPITAL_CHECK=1 で main.py から起動される。

    NOTE (Tier S ゲート): main.py の startup_scheduled_tasks への配線は
    人間によるレビュー後に以下を追加すること:

      # backend/app/main.py 内 startup_scheduled_tasks
      if os.getenv("ENABLE_IDLE_CAPITAL_CHECK", "0") == "1":
          try:
              from app.yield_optimizer.idle_detector import IdleCapitalDetector  # noqa: PLC0415
              await scheduled_manager.start_idle_capital_check(
                  on_error=_make_scheduler_error_handler("idle_capital_check_loop"),
              )
              logger.info("idle_capital_check_loop started")
          except BaseException as exc:
              logger.error("Failed to start idle capital check: %s", exc)

    Args:
        interval_seconds: 実行間隔（秒）。デフォルト 900 秒（15 分）
        on_error: エラー発生時のコールバック
    """
    logger.info("Starting idle capital check loop (interval: %ds)", interval_seconds)

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            def _run_check() -> dict[str, object]:
                try:
                    from app.yield_optimizer.idle_detector import (  # noqa: PLC0415
                        IdleCapitalDetector,
                        get_idle_threshold,
                    )
                    from app.yield_optimizer.morpho_client import MorphoClient  # noqa: PLC0415

                    try:
                        from app.exchange.client import BybitSandboxClient  # noqa: PLC0415
                        from app.exchange.config import (  # noqa: PLC0415
                            get_exchange_settings,
                        )

                        exchange_client: object = BybitSandboxClient(
                            settings=get_exchange_settings()
                        )
                    except Exception as exc_inner:
                        logger.warning(
                            "idle_capital_check_loop: exchange client init failed (fail-open): %s",
                            exc_inner,
                        )
                        exchange_client = None

                    detector = IdleCapitalDetector(
                        exchange_client=exchange_client,
                        morpho_client=MorphoClient(),
                        idle_threshold=get_idle_threshold(),
                    )
                    report = detector.build_report()
                    return {
                        "idle_amount": report.idle_amount,
                        "should_deploy": report.should_deploy,
                        "reason": report.reason,
                    }
                except Exception as exc_inner:
                    logger.warning(
                        "idle_capital_check_loop: check failed (fail-open): %s",
                        exc_inner,
                    )
                    return {"idle_amount": "0", "should_deploy": False, "reason": str(exc_inner)}

            result = await asyncio.to_thread(_run_check)
            if result.get("should_deploy"):
                logger.info(
                    "idle_capital_check_loop: deploy recommended — idle=%s USDC",
                    result.get("idle_amount"),
                )
            else:
                logger.debug(
                    "idle_capital_check_loop: no action — idle=%s reason=%s",
                    result.get("idle_amount"),
                    result.get("reason"),
                )

        except asyncio.CancelledError:
            logger.info("idle_capital_check_loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in idle capital check loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)
            await asyncio.sleep(interval_seconds)


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
