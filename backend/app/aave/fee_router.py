# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/fee_router.py

"""
手数料計算用の FastAPI ルーター定義。

- GET /api/fees/calculate
- GET /api/fees/schedule
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, status

from .fee_calculator import FeeCalculator

router = APIRouter(prefix="/api/fees", tags=["fees"])

_calculator = FeeCalculator()


@router.get(
    "/calculate",
    summary="管理手数料・パフォーマンス手数料を計算する",
)
def calculate_fees(
    aum_usd: str,
    profit_usd: str = "0",
    days: int = 30,
) -> dict[str, object]:
    """
    AUM・利益・日数を受け取り、管理手数料とパフォーマンス手数料を返す。

    :param aum_usd: 運用資産額（USD）文字列
    :param profit_usd: 利益額（USD）文字列（デフォルト "0"）
    :param days: 計算対象日数（デフォルト 30）
    :return: 各手数料と合計手数料
    """
    try:
        aum = Decimal(aum_usd)
        profit = Decimal(profit_usd)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decimal value: {exc}",
        ) from exc

    management = _calculator.calculate_management_fee(aum, days=days)
    performance = _calculator.calculate_performance_fee(profit)
    total = management.fee_usd + performance.fee_usd

    return {
        "management_fee": management.model_dump(),
        "performance_fee": performance.model_dump(),
        "total_fee": str(total),
    }


@router.get(
    "/schedule",
    summary="手数料レートスケジュールを返す",
)
def fee_schedule() -> dict[str, str]:
    """手数料率の定数を JSON で返す。"""
    return {
        "management_fee_annual_rate": str(FeeCalculator.MANAGEMENT_FEE_ANNUAL_RATE),
        "performance_fee_rate": str(FeeCalculator.PERFORMANCE_FEE_RATE),
        "min_aum_usd": str(FeeCalculator.MIN_AUM_USD),
        "description": "Management: 0.5% annual on AUM. Performance: 10% on profit.",
    }
