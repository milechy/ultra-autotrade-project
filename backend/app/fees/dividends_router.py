# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/fees/dividends_router.py
"""ユーザー月次手取り(配当)一覧 API。

GET /api/user/dividends — ログインユーザー自身の fee_transactions.user_takehome_jpy を
月次降順 (最大 24 ヶ月) で返す。user_takehome_usd は usd_jpy_rate で換算
(NULL の場合は 150 をフォールバック)。財務値はすべて Decimal 型 (float 禁止)。
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

from .models import FeeTransaction

router = APIRouter(prefix="/api/user", tags=["dividends"])

# usd_jpy_rate が NULL の月のフォールバックレート (USD→JPY)。
_USD_JPY_FALLBACK = Decimal("150")
_MAX_MONTHS = 24


class DividendItem(BaseModel):
    """1 ヶ月分の手取り。Decimal は JSON 上で文字列としてシリアライズされる。"""

    month: str  # ISO date (例: "2026-06-01")
    user_takehome_jpy: Decimal
    user_takehome_usd: Decimal


class DividendsResponse(BaseModel):
    dividends: list[DividendItem]
    total_jpy: Decimal


@router.get("/dividends", response_model=DividendsResponse, summary="月次手取り(配当)一覧")
def get_dividends(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> DividendsResponse:
    """ログインユーザー自身の月次手取りを降順で返す。0 件でも 200。"""
    rows = db.scalars(
        select(FeeTransaction)
        .where(FeeTransaction.user_id == current_user.id)
        .order_by(FeeTransaction.calculation_month.desc())
        .limit(_MAX_MONTHS)
    ).all()

    items: list[DividendItem] = []
    total_jpy = Decimal("0")
    for row in rows:
        jpy = row.user_takehome_jpy if row.user_takehome_jpy is not None else Decimal("0")
        rate = row.usd_jpy_rate if row.usd_jpy_rate else _USD_JPY_FALLBACK
        usd = (jpy / rate).quantize(Decimal("0.01"))
        items.append(
            DividendItem(
                month=row.calculation_month.isoformat(),
                user_takehome_jpy=jpy,
                user_takehome_usd=usd,
            )
        )
        total_jpy += jpy

    return DividendsResponse(dividends=items, total_jpy=total_jpy)
