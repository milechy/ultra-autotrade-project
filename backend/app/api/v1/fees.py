# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/api/v1/fees.py
"""F-8a: v10 fees API endpoints (read-only 中心 + simulate)。

旧 ``/api/billing/*`` (billing/router.py) と ``/api/fees/calculate|schedule``
(aave/fee_router.py) は **本タスクでは無変更**。F-8b で廃止 + フロント差し替え予定。

新規 endpoints:
- GET  /api/v1/fees/config              認証済み: 現行 active fee_config 取得
- GET  /api/v1/fees/my-summary          自分のみ: 累計手数料サマリ
- GET  /api/v1/fees/my-history          自分のみ: 月別履歴 (最新 N 件)
- POST /api/v1/fees/simulate            認証済み: F-5 calculator 直呼び (DB 書込なし)
- GET  /api/v1/fees/affiliate-earnings  自分のみ: アフィリエイト報酬履歴
- GET  /api/v1/fees/all-users           admin: 全ユーザー手数料一覧
- POST /api/v1/fees/finalize-month      admin: 501 (F-7 で本実装)
- GET  /api/v1/fees/uata-income         admin: UATa 収入集計

設計:
- プロジェクトは sync (SessionLocal) のため、async ではなく sync handler を使用
- Decimal は Pydantic で str に直列化 (フロントは ``Number(str).toFixed()`` で受ける、
  CLAUDE.md "Decimal型 → Number() ラップ" メモリ準拠)
- Pydantic レスポンスは Pydantic v2 の ``model_config = ConfigDict(from_attributes=True)``

関連:
- F-5 ``app.fees.calculator`` (純粋関数エンジン)
- F-1 ``app.billing.v10_models`` (FeeConfigV10 / FeeTransaction)
- F-3 ``app.auth.models`` (RiskMode / InvestmentTier)
- docs/45_fee_model_v10_migration_plan.md §4 F-8 行
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import InvestmentTier, RiskMode, User
from app.billing.v10_models import FeeConfigV10, FeeTransaction
from app.database import get_db
from app.fees import FeeCalculationInput, FeeCalculator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fees", tags=["fees-v10"])

# ===== current month 起点 =====
_FIRST_DAY_OF_MONTH = 1


def _today_month_start() -> date:
    today = date.today()
    return today.replace(day=_FIRST_DAY_OF_MONTH)


# ===========================================================================
# Pydantic schemas
# ===========================================================================


class FeeConfigResponse(BaseModel):
    """現行 active fee_config (v10_default 等)。"""

    config_name: str
    tier_thresholds_jpy: list[int]
    tier_fee_rates: list[float]
    tier_monthly_yield_caps: list[float]
    subscription_rates: dict[str, float]
    expense_markup_enabled: bool
    expense_markup_rate: str  # Decimal → str
    affiliate_rate: str
    is_active: bool
    effective_from: datetime


class FeeSummaryResponse(BaseModel):
    """ユーザー単位の累計サマリ。"""

    user_id: int
    total_fee_paid_jpy: str
    total_subscription_paid_jpy: str
    total_user_takehome_jpy: str
    total_yield_excess_to_uata_jpy: str
    months_count: int


class FeeHistoryItemResponse(BaseModel):
    """月次履歴の 1 行。"""

    model_config = ConfigDict(from_attributes=False)

    calculation_month: date
    tier: str
    risk_mode: str
    deposit_jpy: str
    net_profit_jpy: str
    fee_amount_jpy: str
    subscription_amount_jpy: str
    user_takehome_jpy: str
    finalized_at: datetime | None = None


class AffiliateEarningItemResponse(BaseModel):
    """アフィリエイト報酬の 1 行 (自分が affiliate_id として記録された月)。"""

    calculation_month: date
    invitee_user_id: int
    invitee_subscription_amount_jpy: str
    affiliate_amount_jpy: str
    finalized_at: datetime | None = None


class AllUsersFeeItemResponse(BaseModel):
    """admin 用全ユーザー手数料一覧の 1 行。"""

    user_id: int
    calculation_month: date
    tier: str
    risk_mode: str
    deposit_jpy: str
    net_profit_jpy: str
    fee_amount_jpy: str
    subscription_amount_jpy: str
    user_takehome_jpy: str
    affiliate_id: int | None
    affiliate_amount_jpy: str
    finalized_at: datetime | None


class SimulateRequest(BaseModel):
    """v10 計算シミュレーション入力。DB 書込なし。"""

    deposit_jpy: Decimal = Field(ge=0)
    gross_profit_jpy: Decimal
    expense_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    user_tier: InvestmentTier
    user_risk_mode: RiskMode
    is_first_month: bool = False
    affiliate_id: int | None = None


class SimulateResponse(BaseModel):
    """``FeeCalculationResult`` の API 露出版 (Decimal → str)。"""

    raw_expense_jpy: str  # 実費 (マークアップ前, F-9)
    expense_markup_rate_applied: str  # 適用マークアップ率 (0 なら無効, F-9)
    expense_markup_amount_jpy: str  # マークアップ加算分 (F-9)
    net_profit_jpy: str
    fee_rate_applied: str
    fee_amount_jpy: str
    subscription_rate_applied: str
    subscription_amount_jpy: str
    subscription_protected: bool
    monthly_yield_cap_applied: str
    yield_excess_to_uata_jpy: str
    user_takehome_jpy: str
    affiliate_amount_jpy: str


class UataIncomeResponse(BaseModel):
    """admin 用 UATa 収入集計レスポンス。"""

    month_from: date
    month_to: date
    subscription_total: str
    fee_total: str
    yield_excess_total: str
    affiliate_payout_total: str
    uata_income_total: str  # subscription + fee + yield_excess - affiliate


# ===========================================================================
# Helpers
# ===========================================================================


def _get_active_fee_config(db: Session = Depends(get_db)) -> FeeConfigV10:
    """現行 active な FeeConfigV10 を返す。なければ 503。"""
    stmt = (
        select(FeeConfigV10)
        .where(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .limit(1)
    )
    config = db.execute(stmt).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fee config not initialized. Run scripts/seed_fee_config_v10.py.",
        )
    return config


def _decimal_str(value: Decimal | int | float | None) -> str:
    """Decimal/None を str に直列化 (None → '0')。"""
    if value is None:
        return "0"
    return str(value if isinstance(value, Decimal) else Decimal(str(value)))


# ===========================================================================
# Endpoints
# ===========================================================================


@router.get("/config", response_model=FeeConfigResponse, summary="現行 active fee_config 取得")
def get_fee_config(
    _user: User = Depends(require_active_user),
    config: FeeConfigV10 = Depends(_get_active_fee_config),
) -> FeeConfigResponse:
    return FeeConfigResponse(
        config_name=config.config_name,
        tier_thresholds_jpy=list(config.tier_thresholds_jpy),
        tier_fee_rates=[float(r) for r in config.tier_fee_rates],
        tier_monthly_yield_caps=[float(c) for c in config.tier_monthly_yield_caps],
        subscription_rates={k: float(v) for k, v in config.subscription_rates.items()},
        expense_markup_enabled=config.expense_markup_enabled,
        expense_markup_rate=_decimal_str(config.expense_markup_rate),
        affiliate_rate=_decimal_str(config.affiliate_rate),
        is_active=config.is_active,
        effective_from=config.effective_from,
    )


@router.get(
    "/my-summary",
    response_model=FeeSummaryResponse,
    summary="自分の累計手数料サマリ",
)
def get_my_fee_summary(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> FeeSummaryResponse:
    stmt = select(
        func.count(FeeTransaction.id).label("months_count"),
        func.coalesce(func.sum(FeeTransaction.fee_amount_jpy), 0).label("total_fee"),
        func.coalesce(func.sum(FeeTransaction.subscription_amount_jpy), 0).label("total_sub"),
        func.coalesce(func.sum(FeeTransaction.user_takehome_jpy), 0).label("total_takehome"),
        func.coalesce(func.sum(FeeTransaction.yield_excess_to_uata_jpy), 0).label("total_excess"),
    ).where(FeeTransaction.user_id == user.id)
    row = db.execute(stmt).one()
    return FeeSummaryResponse(
        user_id=user.id,
        total_fee_paid_jpy=_decimal_str(row.total_fee),
        total_subscription_paid_jpy=_decimal_str(row.total_sub),
        total_user_takehome_jpy=_decimal_str(row.total_takehome),
        total_yield_excess_to_uata_jpy=_decimal_str(row.total_excess),
        months_count=int(row.months_count or 0),
    )


@router.get(
    "/my-history",
    response_model=list[FeeHistoryItemResponse],
    summary="自分の月別履歴 (最新 N 件)",
)
def get_my_fee_history(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=24, ge=1, le=120),
) -> list[FeeHistoryItemResponse]:
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.user_id == user.id)
        .order_by(FeeTransaction.calculation_month.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        FeeHistoryItemResponse(
            calculation_month=r.calculation_month,
            tier=r.tier,
            risk_mode=r.risk_mode,
            deposit_jpy=_decimal_str(r.deposit_amount_jpy),
            net_profit_jpy=_decimal_str(r.net_profit_jpy),
            fee_amount_jpy=_decimal_str(r.fee_amount_jpy),
            subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            user_takehome_jpy=_decimal_str(r.user_takehome_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="v10 計算シミュレーション (DB 書込なし)",
)
def simulate_fee(
    payload: SimulateRequest,
    user: User = Depends(require_active_user),
    config: FeeConfigV10 = Depends(_get_active_fee_config),
) -> SimulateResponse:
    calculator = FeeCalculator(config)
    result = calculator.calculate_monthly(
        FeeCalculationInput(
            user_id=user.id,
            calculation_month=_today_month_start(),
            deposit_jpy=payload.deposit_jpy,
            gross_profit_jpy=payload.gross_profit_jpy,
            expense_jpy=payload.expense_jpy,
            user_tier=payload.user_tier,
            user_risk_mode=payload.user_risk_mode,
            affiliate_id=payload.affiliate_id,
            is_first_month=payload.is_first_month,
        )
    )
    return SimulateResponse(
        raw_expense_jpy=_decimal_str(result.raw_expense_jpy),
        expense_markup_rate_applied=_decimal_str(result.expense_markup_rate_applied),
        expense_markup_amount_jpy=_decimal_str(result.expense_markup_amount_jpy),
        net_profit_jpy=_decimal_str(result.net_profit_jpy),
        fee_rate_applied=_decimal_str(result.fee_rate_applied),
        fee_amount_jpy=_decimal_str(result.fee_amount_jpy),
        subscription_rate_applied=_decimal_str(result.subscription_rate_applied),
        subscription_amount_jpy=_decimal_str(result.subscription_amount_jpy),
        subscription_protected=result.subscription_protected,
        monthly_yield_cap_applied=_decimal_str(result.monthly_yield_cap_applied),
        yield_excess_to_uata_jpy=_decimal_str(result.yield_excess_to_uata_jpy),
        user_takehome_jpy=_decimal_str(result.user_takehome_jpy),
        affiliate_amount_jpy=_decimal_str(result.affiliate_amount_jpy),
    )


@router.get(
    "/affiliate-earnings",
    response_model=list[AffiliateEarningItemResponse],
    summary="自分が招待者として記録された月別 affiliate 報酬",
)
def get_my_affiliate_earnings(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=24, ge=1, le=120),
) -> list[AffiliateEarningItemResponse]:
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.affiliate_id == user.id)
        .order_by(FeeTransaction.calculation_month.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AffiliateEarningItemResponse(
            calculation_month=r.calculation_month,
            invitee_user_id=r.user_id,
            invitee_subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            affiliate_amount_jpy=_decimal_str(r.affiliate_amount_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.get(
    "/all-users",
    response_model=list[AllUsersFeeItemResponse],
    summary="全ユーザー手数料一覧 (admin)",
    dependencies=[Depends(require_admin)],
)
def list_all_users_fees(
    db: Session = Depends(get_db),
    month: date | None = Query(
        default=None,
        description="YYYY-MM-DD (月初日)。省略時は今月。",
    ),
) -> list[AllUsersFeeItemResponse]:
    target_month = month or _today_month_start()
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.calculation_month == target_month)
        .order_by(FeeTransaction.user_id)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AllUsersFeeItemResponse(
            user_id=r.user_id,
            calculation_month=r.calculation_month,
            tier=r.tier,
            risk_mode=r.risk_mode,
            deposit_jpy=_decimal_str(r.deposit_amount_jpy),
            net_profit_jpy=_decimal_str(r.net_profit_jpy),
            fee_amount_jpy=_decimal_str(r.fee_amount_jpy),
            subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            user_takehome_jpy=_decimal_str(r.user_takehome_jpy),
            affiliate_id=r.affiliate_id,
            affiliate_amount_jpy=_decimal_str(r.affiliate_amount_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.post(
    "/finalize-month",
    summary="月次 finalize (F-7 で本実装、現状スケルトン)",
    dependencies=[Depends(require_admin)],
)
def finalize_month(month: date) -> dict[str, Any]:
    """F-7 (1214120401388139) で本実装予定。本タスクでは 501 を返すスケルトン。"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Not yet implemented. Will be implemented in F-7 "
            "(Asana 1214120401388139). Requested month: "
            f"{month.isoformat()}"
        ),
    )


@router.get(
    "/uata-income",
    response_model=UataIncomeResponse,
    summary="UATa 収入集計 (admin)",
    dependencies=[Depends(require_admin)],
)
def get_uata_income(
    db: Session = Depends(get_db),
    month_from: date = Query(..., description="開始月初日 (inclusive)"),
    month_to: date = Query(..., description="終了月初日 (inclusive)"),
) -> UataIncomeResponse:
    if month_from > month_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month_from must be <= month_to",
        )
    stmt = select(
        func.coalesce(func.sum(FeeTransaction.subscription_amount_jpy), 0).label("subscription"),
        func.coalesce(func.sum(FeeTransaction.fee_amount_jpy), 0).label("fee"),
        func.coalesce(func.sum(FeeTransaction.yield_excess_to_uata_jpy), 0).label("yield_excess"),
        func.coalesce(func.sum(FeeTransaction.affiliate_amount_jpy), 0).label("affiliate"),
    ).where(
        FeeTransaction.calculation_month >= month_from,
        FeeTransaction.calculation_month <= month_to,
    )
    row = db.execute(stmt).one()
    sub_d = Decimal(str(row.subscription))
    fee_d = Decimal(str(row.fee))
    excess_d = Decimal(str(row.yield_excess))
    aff_d = Decimal(str(row.affiliate))
    uata = sub_d + fee_d + excess_d - aff_d
    return UataIncomeResponse(
        month_from=month_from,
        month_to=month_to,
        subscription_total=_decimal_str(sub_d),
        fee_total=_decimal_str(fee_d),
        yield_excess_total=_decimal_str(excess_d),
        affiliate_payout_total=_decimal_str(aff_d),
        uata_income_total=_decimal_str(uata),
    )
