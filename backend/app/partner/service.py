# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/service.py
"""パートナー配下ユーザー運用実績集計サービス。"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.models import User
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot

from .schemas import MonthlyStatsResponse, PartnerStatsResponse, UserStatsResponse


def _get_partner_user_ids(db: Session, partner_id: int) -> list[int]:
    """users.invited_by からパートナーに紐づくユーザー ID を取得する。

    マルチユース招待コード対応: Invitation.invited_user_id（1件のみ）ではなく
    users.invited_by（ユーザーごとに記録）を参照する。
    """
    users = db.query(User.id).filter(User.invited_by == partner_id).all()
    return [u.id for u in users]


def get_partner_stats(db: Session, partner_id: int) -> PartnerStatsResponse:
    """
    パートナー配下ユーザー全体の KPI を集計する。

    - total_aum: 各ユーザーの最新スナップショット合計
    - yesterday_aum: 前日の最新スナップショット合計
    - month_return_pct: 当月の月次 portfolio_history から算出
    - yesterday_return_pct: 前日の日次 portfolio_history から算出
    - user_count: 招待ユーザー数
    """
    user_ids = _get_partner_user_ids(db, partner_id)
    user_count = len(user_ids)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    total_aum = Decimal("0")
    yesterday_aum = Decimal("0")

    if user_ids:
        for uid in user_ids:
            snap = (
                db.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.user_id == uid)
                .order_by(PortfolioSnapshot.recorded_at.desc())
                .first()
            )
            if snap is not None:
                total_aum += Decimal(str(snap.total_value_usd))

            ysnap = (
                db.query(PortfolioSnapshot)
                .filter(
                    PortfolioSnapshot.user_id == uid,
                    PortfolioSnapshot.recorded_at >= yesterday_start,
                    PortfolioSnapshot.recorded_at < today_start,
                )
                .order_by(PortfolioSnapshot.recorded_at.desc())
                .first()
            )
            if ysnap is not None:
                yesterday_aum += Decimal(str(ysnap.total_value_usd))

    yesterday_return_pct: Optional[Decimal] = None
    month_return_pct: Optional[Decimal] = None

    if user_ids:
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        daily_records = (
            db.query(PortfolioHistory)
            .filter(
                PortfolioHistory.user_id.in_(user_ids),
                PortfolioHistory.period_type == "daily",
                PortfolioHistory.period_start >= yesterday_start,
                PortfolioHistory.period_start < today_start,
            )
            .all()
        )
        if daily_records:
            total_open = Decimal("0")
            total_close = Decimal("0")
            for r in daily_records:
                total_open += Decimal(str(r.open_value_usd))
                total_close += Decimal(str(r.close_value_usd))
            if total_open > Decimal("0"):
                yesterday_return_pct = (
                    (total_close - total_open) / total_open * Decimal("100")
                ).quantize(Decimal("0.0001"))

        monthly_records = (
            db.query(PortfolioHistory)
            .filter(
                PortfolioHistory.user_id.in_(user_ids),
                PortfolioHistory.period_type == "monthly",
                PortfolioHistory.period_start >= month_start,
            )
            .all()
        )
        if monthly_records:
            total_open = Decimal("0")
            total_close = Decimal("0")
            for r in monthly_records:
                total_open += Decimal(str(r.open_value_usd))
                total_close += Decimal(str(r.close_value_usd))
            if total_open > Decimal("0"):
                month_return_pct = (
                    (total_close - total_open) / total_open * Decimal("100")
                ).quantize(Decimal("0.0001"))

    return PartnerStatsResponse(
        total_aum=total_aum,
        yesterday_aum=yesterday_aum,
        month_return_pct=month_return_pct,
        yesterday_return_pct=yesterday_return_pct,
        user_count=user_count,
    )


def get_user_stats(db: Session, partner_id: int, user_id: int) -> UserStatsResponse:
    """
    特定ユーザーの運用実績を返す。

    招待テーブルで partner_id との紐づきを確認する。
    紐づきがない場合は ValueError を送出する。
    """
    # users.invited_by でパートナーとの紐づきを確認（マルチユース招待コード対応）
    target_user = db.query(User).filter(User.id == user_id, User.invited_by == partner_id).first()
    if target_user is None:
        raise ValueError(f"User {user_id} is not invited by partner {partner_id}")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    snap = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user_id)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .first()
    )
    today_amount = Decimal(str(snap.total_value_usd)) if snap is not None else Decimal("0")

    month_snap = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.recorded_at >= month_start,
        )
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .first()
    )
    month_amount = (
        Decimal(str(month_snap.total_value_usd)) if month_snap is not None else today_amount
    )

    yesterday_history = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id == user_id,
            PortfolioHistory.period_type == "daily",
            PortfolioHistory.period_start >= yesterday_start,
            PortfolioHistory.period_start < today_start,
        )
        .first()
    )
    yesterday_return_pct: Optional[Decimal] = (
        Decimal(str(yesterday_history.pnl_pct)) if yesterday_history is not None else None
    )

    month_history = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id == user_id,
            PortfolioHistory.period_type == "monthly",
            PortfolioHistory.period_start >= month_start,
        )
        .first()
    )
    month_return_pct: Optional[Decimal] = (
        Decimal(str(month_history.pnl_pct)) if month_history is not None else None
    )

    return UserStatsResponse(
        user_id=user_id,
        today_amount=today_amount,
        month_amount=month_amount,
        yesterday_return_pct=yesterday_return_pct,
        month_return_pct=month_return_pct,
    )


@dataclass
class _MonthlyAgg:
    open_value: Decimal = dc_field(default_factory=lambda: Decimal("0"))
    close_value: Decimal = dc_field(default_factory=lambda: Decimal("0"))
    users: set[int] = dc_field(default_factory=set)


def get_monthly_stats(db: Session, partner_id: int) -> list[MonthlyStatsResponse]:
    """
    パートナー配下ユーザーの月別運用実績を集計して返す。

    portfolio_history の period_type='monthly' レコードを月ごとに合算する。
    """
    user_ids = _get_partner_user_ids(db, partner_id)
    if not user_ids:
        return []

    records = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id.in_(user_ids),
            PortfolioHistory.period_type == "monthly",
        )
        .order_by(PortfolioHistory.period_start.asc())
        .all()
    )

    agg: dict[str, _MonthlyAgg] = {}
    for r in records:
        period_start = r.period_start
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
        month_key = period_start.strftime("%Y-%m")
        if month_key not in agg:
            agg[month_key] = _MonthlyAgg()
        agg[month_key].open_value += Decimal(str(r.open_value_usd))
        agg[month_key].close_value += Decimal(str(r.close_value_usd))
        agg[month_key].users.add(r.user_id)

    result: list[MonthlyStatsResponse] = []
    for month_key in sorted(agg.keys()):
        a = agg[month_key]
        if a.open_value > Decimal("0"):
            return_pct = ((a.close_value - a.open_value) / a.open_value * Decimal("100")).quantize(
                Decimal("0.0001")
            )
        else:
            return_pct = Decimal("0")
        result.append(
            MonthlyStatsResponse(
                month=month_key,
                start_value=a.open_value,
                end_value=a.close_value,
                return_pct=return_pct,
                user_count=len(a.users),
            )
        )

    return result
