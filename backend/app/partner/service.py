# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/partner/service.py
"""パートナー配下ユーザー運用実績集計サービス。"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.models import AIDecision
from app.auth.models import User
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot

from .schemas import (
    JudgmentSummaryItem,
    MonthlyStatsResponse,
    PartnerStatsResponse,
    ReferralUserDetailResponse,
    ReferralUserItem,
    UserStatsResponse,
)


def _get_partner_user_ids(db: Session, partner_id: int) -> list[int]:
    """users.referrer_id からパートナーに紐づくユーザー ID を取得する (RAS B モデル)。"""
    users = db.query(User.id).filter(User.referrer_id == partner_id).all()
    return [u.id for u in users]


def _mask_email(email: str) -> str:
    """``y***@example.com`` 形式へマスクする。"""
    if "@" not in email:
        return email[:1] + "***"
    local, domain = email.split("@", 1)
    return (f"{local[0]}***@{domain}") if local else f"***@{domain}"


def get_partner_stats(db: Session, partner_id: int) -> PartnerStatsResponse:
    """
    パートナー配下ユーザー全体の KPI を集計する。

    - total_aum: 各ユーザーの最新スナップショット合計
    - yesterday_aum: 前日の最新スナップショット合計
    - month_return_pct: 当月の月次 portfolio_history から算出
    - yesterday_return_pct: 前日の日次 portfolio_history から算出
    - user_count: 被紹介ユーザー数 (referrer_id)
    - total_pnl: 当月の pnl_usd 合計
    - active_user_count: is_active=True の被紹介ユーザー数
    """
    user_ids = _get_partner_user_ids(db, partner_id)
    user_count = len(user_ids)

    active_user_count: int = (
        db.query(func.count(User.id))
        .filter(User.referrer_id == partner_id, User.is_active.is_(True))
        .scalar()
    ) or 0

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
    total_pnl: Optional[Decimal] = None

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
            pnl_sum = Decimal("0")
            for r in monthly_records:
                total_open += Decimal(str(r.open_value_usd))
                total_close += Decimal(str(r.close_value_usd))
                pnl_sum += Decimal(str(r.pnl_usd))
            if total_open > Decimal("0"):
                month_return_pct = (
                    (total_close - total_open) / total_open * Decimal("100")
                ).quantize(Decimal("0.0001"))
            total_pnl = pnl_sum

    return PartnerStatsResponse(
        total_aum=total_aum,
        yesterday_aum=yesterday_aum,
        month_return_pct=month_return_pct,
        yesterday_return_pct=yesterday_return_pct,
        user_count=user_count,
        total_pnl=total_pnl,
        active_user_count=active_user_count,
    )


def get_user_stats(db: Session, partner_id: int, user_id: int) -> UserStatsResponse:
    """
    特定ユーザーの運用実績を返す。

    referrer_id で partner_id との紐づきを確認する。
    紐づきがない場合は ValueError を送出する。
    """
    target_user = db.query(User).filter(User.id == user_id, User.referrer_id == partner_id).first()
    if target_user is None:
        raise ValueError(f"User {user_id} is not referred by partner {partner_id}")

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


def list_referral_users(db: Session, partner_id: int) -> list[ReferralUserItem]:
    """
    被紹介者一覧を N+1 なしで返す (3 クエリ)。

    Q1: referrer_id からユーザー一覧
    Q2: 各ユーザーの最新スナップショット (subquery)
    Q3: 当月の月次 portfolio_history から利回り計算
    """
    users = (
        db.query(User).filter(User.referrer_id == partner_id).order_by(User.created_at.desc()).all()
    )
    if not users:
        return []

    user_ids = [u.id for u in users]

    max_snap_sq = (
        db.query(
            PortfolioSnapshot.user_id,
            func.max(PortfolioSnapshot.recorded_at).label("max_ts"),
        )
        .filter(PortfolioSnapshot.user_id.in_(user_ids))
        .group_by(PortfolioSnapshot.user_id)
        .subquery()
    )
    snaps = (
        db.query(PortfolioSnapshot)
        .join(
            max_snap_sq,
            (PortfolioSnapshot.user_id == max_snap_sq.c.user_id)
            & (PortfolioSnapshot.recorded_at == max_snap_sq.c.max_ts),
        )
        .all()
    )
    snap_map: dict[int, Decimal] = {s.user_id: Decimal(str(s.total_value_usd)) for s in snaps}

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_recs = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id.in_(user_ids),
            PortfolioHistory.period_type == "monthly",
            PortfolioHistory.period_start >= month_start,
        )
        .all()
    )
    month_ret_map: dict[int, Optional[Decimal]] = {}
    for rec in monthly_recs:
        open_val = Decimal(str(rec.open_value_usd))
        if open_val > Decimal("0"):
            close_val = Decimal(str(rec.close_value_usd))
            pct = (close_val - open_val) / open_val * Decimal("100")
            month_ret_map[rec.user_id] = pct.quantize(Decimal("0.0001"))

    return [
        ReferralUserItem(
            user_id=u.id,
            email_masked=_mask_email(u.email),
            total_aum=snap_map.get(u.id, Decimal("0")),
            month_return_pct=month_ret_map.get(u.id),
            is_active=u.is_active,
            last_judgment_at=u.last_judgment_at,
        )
        for u in users
    ]


def get_referral_user_detail(
    db: Session, partner_id: int, user_id: int
) -> ReferralUserDetailResponse:
    """
    被紹介者の詳細を返す。

    - referrer_id で partner_id との紐づきを確認
    - 月別運用実績 (portfolio_history monthly)
    - AI 判定履歴要約 (ai_decisions 直近 10 件)
    """
    user = db.query(User).filter(User.id == user_id, User.referrer_id == partner_id).first()
    if user is None:
        raise ValueError(f"User {user_id} is not referred by partner {partner_id}")

    monthly_records = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id == user_id,
            PortfolioHistory.period_type == "monthly",
        )
        .order_by(PortfolioHistory.period_start.asc())
        .all()
    )
    monthly_performance = [
        MonthlyStatsResponse(
            month=r.period_start.strftime("%Y-%m"),
            start_value=Decimal(str(r.open_value_usd)),
            end_value=Decimal(str(r.close_value_usd)),
            return_pct=Decimal(str(r.pnl_pct)),
            user_count=1,
        )
        for r in monthly_records
    ]

    decisions = (
        db.query(AIDecision)
        .filter(AIDecision.user_id == user_id)
        .order_by(AIDecision.created_at.desc())
        .limit(10)
        .all()
    )
    judgment_summary = [
        JudgmentSummaryItem(
            action=d.action,
            confidence=d.confidence,
            created_at=d.created_at,
        )
        for d in decisions
    ]

    return ReferralUserDetailResponse(
        user_id=user_id,
        email_masked=_mask_email(user.email),
        monthly_performance=monthly_performance,
        judgment_summary=judgment_summary,
    )
