# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/monthly_fee_batch.py
"""F-7: 月末バッチ処理 (月間手数料計算)。

毎月最終日 23:55 JST に実行され、active な ``FundAllocation`` を持つ全ユーザーに
ついて月間手数料を計算し ``fee_transactions`` に書き込む。F-5 ``FeeCalculator``
(純粋関数) を再利用し、本モジュールは I/O 層 (DB 集計 / Slack 通知 /
スケジューリング) に専念する。

責務:
- active ``FundAllocation`` を ``user_id`` でロールアップ → ``deposit_jpy`` 算出
- ``FeeConfigV10`` (active) を取得し ``FeeCalculator`` を初期化
- ユーザー単位に ``calculate_monthly()`` を呼び ``FeeTransaction`` を作成
- 単一ユーザーの失敗は他ユーザーに影響させない (個別 try/except + ロールバック)
- 月次 unique 制約 (``uq_fee_tx_user_month``) を尊重: 既存レコードは更新せずスキップ
- バッチ開始 / 完了 / 失敗を Slack ``#ultra-auto-project`` に通知

呼び出し元:
- ``main.py`` の startup hook → ``monthly_fee_batch_loop()`` (毎月最終日 23:55 JST)
- ``POST /api/v1/fees/finalize-month`` (admin) → ``run_monthly_fee_batch(month)``

Decimal 厳守 (CLAUDE.md §Security Rules #11): float に絶対変換しない。
"""

from __future__ import annotations

import asyncio
import calendar
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.models import RiskMode, User, normalize_tier
from app.billing.v10_models import FeeConfigV10, FeeTransaction
from app.database import SessionLocal
from app.fees import FeeCalculationInput, FeeCalculator
from app.partner.allocation_models import FundAllocation
from app.portfolio.models import PortfolioHistory

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: JST タイムゾーン (バッチ実行・月境界判定で使用)。
JST = timezone(timedelta(hours=9))

#: バッチ実行時刻 (JST)。最終日 23:55:00 JST。
BATCH_HOUR_JST = 23
BATCH_MINUTE_JST = 55

#: USD → JPY 換算レート (env override 可)。``exchange/config.py`` と同じ既定値を使用。
_DEFAULT_USD_TO_JPY_RATE = Decimal("150")

#: スケジューラー実行状態 (運用監視用、必要なら /health 経由で参照)。
_loop_started: bool = False
_last_run_at: "datetime | None" = None
_next_run_at: "datetime | None" = None
_last_error_msg: "str | None" = None


def get_batch_status() -> dict[str, Any]:
    """月末バッチの稼働状態を返す (運用監視用)。"""
    return {
        "running": _loop_started,
        "last_run": _last_run_at.isoformat() if _last_run_at else None,
        "next_run": _next_run_at.isoformat() if _next_run_at else None,
        "last_error": _last_error_msg,
    }


# ===========================================================================
# Result / summary dataclasses
# ===========================================================================


@dataclass
class MonthlyFeeBatchEntry:
    """1 ユーザー分の処理結果 (成功 or 失敗)。"""

    user_id: int
    status: str  # "created" / "skipped_existing" / "failed"
    fee_amount_jpy: Decimal = Decimal("0")
    subscription_amount_jpy: Decimal = Decimal("0")
    user_takehome_jpy: Decimal = Decimal("0")
    error: str | None = None


@dataclass
class MonthlyFeeBatchSummary:
    """バッチ全体のサマリ。"""

    target_month: date
    started_at: datetime
    finished_at: datetime
    processed_count: int = 0
    created_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    total_fee_jpy: Decimal = Decimal("0")
    total_subscription_jpy: Decimal = Decimal("0")
    total_takehome_jpy: Decimal = Decimal("0")
    entries: list[MonthlyFeeBatchEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_log_dict(self) -> dict[str, Any]:
        """Slack / ログ向けの軽量化辞書 (entries は件数のみに圧縮)。"""
        d = asdict(self)
        # entries は人数が多いと長文になるためサマリで返す
        d["entries"] = [
            {
                "user_id": e["user_id"],
                "status": e["status"],
                "fee": str(e["fee_amount_jpy"]),
            }
            for e in d.get("entries", [])
        ]
        # Decimal を str 化 (JSON 直列化対応)
        for key in ("total_fee_jpy", "total_subscription_jpy", "total_takehome_jpy"):
            d[key] = str(d[key])
        d["target_month"] = self.target_month.isoformat()
        d["started_at"] = self.started_at.isoformat()
        d["finished_at"] = self.finished_at.isoformat()
        return d


# ===========================================================================
# Slack notification (fail-open)
# ===========================================================================


def _post_slack(text: str) -> None:
    """Slack webhook に通知する。失敗してもバッチは継続 (fail-open)。"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.debug("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return
    try:
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - webhook_url は環境変数経由
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)  # noqa: S310
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Slack notification failed: %s", exc)


# ===========================================================================
# JST month helpers
# ===========================================================================


def _now_jst() -> datetime:
    return datetime.now(JST)


def month_start(target: date) -> date:
    """``target`` の月初日 (1 日)。``calculation_month`` のキー値。"""
    return target.replace(day=1)


def month_end(target: date) -> date:
    """``target`` の月末日 (月の最終日)。"""
    last_day = calendar.monthrange(target.year, target.month)[1]
    return target.replace(day=last_day)


def previous_month_start(target: date) -> date:
    """``target`` の前月の月初日。"""
    first = month_start(target)
    last_day_prev = first - timedelta(days=1)
    return last_day_prev.replace(day=1)


def next_batch_run_jst(now: datetime | None = None) -> datetime:
    """次回バッチ実行時刻 (月末日 23:55 JST) を返す。

    ``now`` が当月最終日 23:55 JST 以前なら当月を返す。それ以降なら翌月最終日。
    JST naive な ``now`` が渡された場合は ``JST`` を補完する (テスト容易性向上)。
    """
    if now is None:
        now = _now_jst()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    else:
        now = now.astimezone(JST)

    candidate_date = month_end(now.date())
    candidate = datetime.combine(
        candidate_date,
        time(BATCH_HOUR_JST, BATCH_MINUTE_JST, 0, tzinfo=JST),
    )
    if now >= candidate:
        # 当月最終日 23:55 を越えた → 翌月最終日に進める
        next_month_first = (candidate_date + timedelta(days=1)).replace(day=1)
        candidate_date = month_end(next_month_first)
        candidate = datetime.combine(
            candidate_date,
            time(BATCH_HOUR_JST, BATCH_MINUTE_JST, 0, tzinfo=JST),
        )
    return candidate


# ===========================================================================
# Data lookups
# ===========================================================================


def _get_usd_to_jpy_rate() -> Decimal:
    """USD → JPY 換算レート。``exchange.config`` と同じ環境変数キーを使用。"""
    raw = os.getenv("USD_TO_JPY_RATE")
    if not raw:
        return _DEFAULT_USD_TO_JPY_RATE
    try:
        return Decimal(raw)
    except Exception:
        logger.warning(
            "Invalid USD_TO_JPY_RATE=%r; falling back to %s", raw, _DEFAULT_USD_TO_JPY_RATE
        )
        return _DEFAULT_USD_TO_JPY_RATE


def _get_active_fee_config(db: "Session") -> FeeConfigV10:
    """active な ``FeeConfigV10`` を 1 行返す。なければ ``RuntimeError``。"""
    stmt = (
        select(FeeConfigV10)
        .where(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .limit(1)
    )
    config = db.execute(stmt).scalar_one_or_none()
    if config is None:
        raise RuntimeError(
            "No active FeeConfigV10 found. Run scripts/seed_fee_config_v10.py before batch."
        )
    return config


def _get_active_user_deposits_jpy(db: "Session", *, fx_rate: Decimal) -> dict[int, Decimal]:
    """active な ``FundAllocation`` を ``user_id`` でロールアップして ``deposit_jpy`` を返す。

    ``tester_user_id`` が NULL の割り振りはスキップ (legacy データ)。``user_id`` キーは
    ``FundAllocation.tester_user_id`` (パートナー配下のテスター)。
    """
    stmt = (
        select(
            FundAllocation.tester_user_id,
            func.sum(FundAllocation.allocated_amount_usd).label("total_usd"),
        )
        .where(
            FundAllocation.status == "active",
            FundAllocation.tester_user_id.is_not(None),
        )
        .group_by(FundAllocation.tester_user_id)
    )
    deposits: dict[int, Decimal] = {}
    for row in db.execute(stmt).all():
        if row.tester_user_id is None:
            continue
        usd = Decimal(str(row.total_usd or 0))
        deposits[int(row.tester_user_id)] = (usd * fx_rate).quantize(Decimal("1"))
    return deposits


def _get_monthly_gross_profit_jpy(
    db: "Session",
    *,
    user_id: int,
    target_month: date,
    fx_rate: Decimal,
) -> Decimal:
    """対象月の gross profit (JPY) を ``portfolio_history`` から取得する。

    ``period_type='monthly'`` かつ ``period_start`` が対象月の月初日と一致するレコードの
    ``pnl_usd`` を JPY 換算して返す。レコードがなければ ``Decimal('0')`` (実損益不明 →
    手数料発生なし、サブスク保護で UATa 行きになる)。
    """
    target = month_start(target_month)
    next_first = month_start(target + timedelta(days=32))
    stmt = (
        select(PortfolioHistory.pnl_usd)
        .where(
            PortfolioHistory.user_id == user_id,
            PortfolioHistory.period_type == "monthly",
            PortfolioHistory.period_start >= datetime.combine(target, time.min, tzinfo=JST),
            PortfolioHistory.period_start < datetime.combine(next_first, time.min, tzinfo=JST),
        )
        .order_by(PortfolioHistory.period_start.desc())
        .limit(1)
    )
    pnl_usd = db.execute(stmt).scalar_one_or_none()
    if pnl_usd is None:
        return Decimal("0")
    return (Decimal(str(pnl_usd)) * fx_rate).quantize(Decimal("1"))


def _is_first_month_for_user(db: "Session", user_id: int) -> bool:
    """対象ユーザーに過去 ``FeeTransaction`` が一切無ければ初月扱い (subscription 0)。"""
    stmt = select(func.count(FeeTransaction.id)).where(FeeTransaction.user_id == user_id)
    count = db.execute(stmt).scalar_one()
    return int(count or 0) == 0


def _user_already_has_month(db: "Session", *, user_id: int, calculation_month: date) -> bool:
    """既に同月レコードがある (= 二重実行 / 手動 finalize 後) なら True。"""
    stmt = select(func.count(FeeTransaction.id)).where(
        FeeTransaction.user_id == user_id,
        FeeTransaction.calculation_month == calculation_month,
    )
    return int(db.execute(stmt).scalar_one() or 0) > 0


def _resolve_risk_mode(raw: str | None) -> RiskMode:
    """``users.risk_mode`` を ``RiskMode`` enum に正規化 (NULL → CONSERVATIVE)。"""
    if not raw:
        return RiskMode.CONSERVATIVE
    try:
        return RiskMode(raw)
    except ValueError:
        logger.warning("Unknown risk_mode=%r, falling back to CONSERVATIVE", raw)
        return RiskMode.CONSERVATIVE


# ===========================================================================
# Core batch
# ===========================================================================


def _process_user(
    db: "Session",
    *,
    user: User,
    calculator: FeeCalculator,
    target_month: date,
    deposit_jpy: Decimal,
    fx_rate: Decimal,
) -> MonthlyFeeBatchEntry:
    """単一ユーザーの月次手数料を計算し ``FeeTransaction`` を作成する。

    既存レコードがあれば更新せずスキップ (idempotent)。例外発生時は呼び出し元で
    rollback されるよう、ここでは flush で IntegrityError を早期検出する。
    """
    if _user_already_has_month(db, user_id=user.id, calculation_month=target_month):
        logger.info(
            "monthly_fee_batch: skipping existing record user_id=%d month=%s",
            user.id,
            target_month,
        )
        return MonthlyFeeBatchEntry(user_id=user.id, status="skipped_existing")

    gross_profit_jpy = _get_monthly_gross_profit_jpy(
        db, user_id=user.id, target_month=target_month, fx_rate=fx_rate
    )
    tier = normalize_tier(user.tier, user_id=user.id)
    risk_mode = _resolve_risk_mode(user.risk_mode)
    is_first = _is_first_month_for_user(db, user.id)

    payload = FeeCalculationInput(
        user_id=user.id,
        calculation_month=target_month,
        deposit_jpy=deposit_jpy,
        gross_profit_jpy=gross_profit_jpy,
        expense_jpy=Decimal("0"),
        user_tier=tier,
        user_risk_mode=risk_mode,
        affiliate_id=user.invited_by,
        is_first_month=is_first,
    )
    result = calculator.calculate_monthly(payload)

    tx = FeeTransaction(
        user_id=result.user_id,
        calculation_month=result.calculation_month,
        tier=result.tier,
        risk_mode=result.risk_mode,
        deposit_amount_jpy=result.deposit_jpy,
        gross_profit_jpy=result.gross_profit_jpy,
        expense_jpy=result.expense_jpy,
        net_profit_jpy=result.net_profit_jpy,
        fee_rate_applied=result.fee_rate_applied,
        fee_amount_jpy=result.fee_amount_jpy,
        subscription_rate_applied=result.subscription_rate_applied,
        subscription_amount_jpy=result.subscription_amount_jpy,
        subscription_protected=result.subscription_protected,
        monthly_yield_cap_applied=result.monthly_yield_cap_applied,
        yield_excess_to_uata_jpy=result.yield_excess_to_uata_jpy,
        user_takehome_jpy=result.user_takehome_jpy,
        affiliate_id=result.affiliate_id,
        affiliate_amount_jpy=result.affiliate_amount_jpy,
        finalized_at=None,
    )
    db.add(tx)
    db.flush()  # uq_fee_tx_user_month を即時検出

    return MonthlyFeeBatchEntry(
        user_id=result.user_id,
        status="created",
        fee_amount_jpy=result.fee_amount_jpy,
        subscription_amount_jpy=result.subscription_amount_jpy,
        user_takehome_jpy=result.user_takehome_jpy,
    )


def run_monthly_fee_batch(
    target_month: date | None = None,
    *,
    db: "Session | None" = None,
    notify_slack: bool = True,
) -> MonthlyFeeBatchSummary:
    """月末バッチを同期実行する。

    Args:
        target_month: 対象月 (任意の日付、内部で月初日に正規化)。``None`` なら
            JST 現在時刻の月を対象とする (= スケジュール実行: 月末日 23:55 JST に
            "今月分" を計算)。
        db: テスト用の外部セッション。``None`` のとき本関数が ``SessionLocal()`` を
            起こし、commit/rollback まで責任を持つ。
        notify_slack: Slack 通知を行うか (テストでは False を指定)。

    Returns:
        ``MonthlyFeeBatchSummary``
    """
    started_at = datetime.now(timezone.utc)
    if target_month is None:
        target_month = month_start(_now_jst().date())
    else:
        target_month = month_start(target_month)

    summary = MonthlyFeeBatchSummary(
        target_month=target_month,
        started_at=started_at,
        finished_at=started_at,
    )

    if notify_slack:
        _post_slack(f"🔔 [Ultra AutoTrade] 月末バッチ開始: {target_month.isoformat()} (F-7)")

    own_session = db is None
    if own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    try:
        config = _get_active_fee_config(db)
        calculator = FeeCalculator(config)
        fx_rate = _get_usd_to_jpy_rate()
        deposits = _get_active_user_deposits_jpy(db, fx_rate=fx_rate)

        if not deposits:
            logger.info("monthly_fee_batch: no active fund_allocations to process")
        else:
            users = (
                db.execute(select(User).where(User.id.in_(list(deposits.keys())))).scalars().all()
            )
            users_by_id = {u.id: u for u in users}

            for user_id, deposit_jpy in deposits.items():
                user = users_by_id.get(user_id)
                if user is None:
                    msg = f"user_id={user_id}: user record not found"
                    summary.errors.append(msg)
                    summary.entries.append(
                        MonthlyFeeBatchEntry(user_id=user_id, status="failed", error=msg)
                    )
                    summary.failed_count += 1
                    continue

                # SAVEPOINT で 1 ユーザー単位にロールバック (他ユーザーへの伝播を防ぐ)
                savepoint = db.begin_nested()
                try:
                    entry = _process_user(
                        db,
                        user=user,
                        calculator=calculator,
                        target_month=target_month,
                        deposit_jpy=deposit_jpy,
                        fx_rate=fx_rate,
                    )
                    savepoint.commit()
                except IntegrityError as exc:
                    savepoint.rollback()
                    msg = f"user_id={user_id}: integrity error ({exc.orig})"
                    summary.errors.append(msg)
                    summary.entries.append(
                        MonthlyFeeBatchEntry(user_id=user_id, status="failed", error=msg)
                    )
                    summary.failed_count += 1
                    logger.error(msg)
                    continue
                except Exception as exc:  # noqa: BLE001
                    savepoint.rollback()
                    msg = f"user_id={user_id}: {type(exc).__name__}: {exc}"
                    summary.errors.append(msg)
                    summary.entries.append(
                        MonthlyFeeBatchEntry(user_id=user_id, status="failed", error=msg)
                    )
                    summary.failed_count += 1
                    logger.error(msg)
                    continue

                summary.entries.append(entry)
                summary.processed_count += 1
                if entry.status == "created":
                    summary.created_count += 1
                    summary.total_fee_jpy += entry.fee_amount_jpy
                    summary.total_subscription_jpy += entry.subscription_amount_jpy
                    summary.total_takehome_jpy += entry.user_takehome_jpy
                elif entry.status == "skipped_existing":
                    summary.skipped_count += 1

        db.commit()

    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: S110
            pass
        summary.failed_count += 1
        summary.errors.append(f"batch fatal: {type(exc).__name__}: {exc}")
        summary.finished_at = datetime.now(timezone.utc)
        if notify_slack:
            _post_slack(
                f"❌ [Ultra AutoTrade] 月末バッチ失敗: {target_month.isoformat()}\n"
                f"原因: {type(exc).__name__}: {exc}"
            )
        logger.error("monthly_fee_batch fatal: %s", exc)
        raise
    finally:
        if own_session:
            db.close()

    summary.finished_at = datetime.now(timezone.utc)

    if notify_slack:
        text = (
            f"✅ [Ultra AutoTrade] 月末バッチ完了: {target_month.isoformat()}\n"
            f"作成: {summary.created_count} / "
            f"スキップ: {summary.skipped_count} / "
            f"失敗: {summary.failed_count}\n"
            f"合計手数料: {summary.total_fee_jpy} JPY / "
            f"合計サブスク: {summary.total_subscription_jpy} JPY"
        )
        _post_slack(text)

    return summary


# ===========================================================================
# Async loop (startup hook)
# ===========================================================================


def _is_loop_enabled() -> bool:
    """``DISABLE_MONTHLY_FEE_BATCH=1`` 以外はデフォルト有効。

    ``ENABLE_MONTHLY_FEE_BATCH=0`` も後方互換として無効化する (CLAUDE.md
    2026-04-02 の "DISABLE_*=1" 方式に揃える)。
    """
    if os.getenv("DISABLE_MONTHLY_FEE_BATCH", "0") == "1":
        return False
    if os.getenv("ENABLE_MONTHLY_FEE_BATCH") == "0":
        return False
    return True


async def monthly_fee_batch_loop(
    sleep_after_run_seconds: int = 60,
    on_error: Optional[Any] = None,
) -> None:
    """月末日 23:55 JST に ``run_monthly_fee_batch`` を発火する常駐ループ。

    実装方針:
    - APScheduler を新規導入せず、``asyncio.sleep`` で次回実行時刻まで待つ
    - 起動直後 / 実行直後とも ``next_batch_run_jst()`` で次回 datetime を求める
    - 実行は ``run_in_executor`` で同期関数を別スレッドに逃がす
    - ``DISABLE_MONTHLY_FEE_BATCH=1`` 設定時はループ自体起動しない (caller 判定)

    Args:
        sleep_after_run_seconds: 実行直後の二重起動防止クッションの待機秒数。
        on_error: 失敗時のコールバック (Slack 通知など)。``Exception`` を 1 引数で受ける。
    """
    global _loop_started, _last_run_at, _next_run_at, _last_error_msg
    _loop_started = True
    while True:
        try:
            now = _now_jst()
            target = next_batch_run_jst(now)
            _next_run_at = target.astimezone(timezone.utc)
            wait_seconds = max(1.0, (target - now).total_seconds())
            logger.info(
                "monthly_fee_batch: next run scheduled at %s JST (in %.1f sec)",
                target.isoformat(),
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

            loop = asyncio.get_running_loop()
            target_month = month_start(target.date())
            summary = await loop.run_in_executor(
                None, lambda: run_monthly_fee_batch(target_month=target_month)
            )
            _last_run_at = datetime.now(timezone.utc)
            _last_error_msg = None
            logger.info("monthly_fee_batch completed: %s", summary.to_log_dict())

            # 同じ日に二度発火しないよう少し休む (sleep_after_run_seconds)
            await asyncio.sleep(sleep_after_run_seconds)

        except asyncio.CancelledError:
            logger.info("monthly_fee_batch loop cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            _last_error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("monthly_fee_batch loop error: %s", exc)
            if on_error is not None:
                try:
                    on_error(exc)
                except Exception as cb_exc:  # noqa: BLE001
                    logger.error("monthly_fee_batch on_error callback failed: %s", cb_exc)
            # 失敗時は短時間だけ待って再トライ (連続失敗で CPU 焼かない)
            await asyncio.sleep(300)
