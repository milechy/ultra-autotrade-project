# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/router.py
"""
Billing モジュールの FastAPI ルーター。

エンドポイント:
- GET  /api/billing/fees     : ユーザーの手数料履歴
- GET  /api/billing/summary  : ユーザーの手数料累計サマリー
- POST /api/billing/batch/daily : 日次手数料バッチ実行（管理者のみ）
- GET  /api/billing/config   : 現在の手数料設定

Admin endpoints (F-12):
- GET  /api/billing/admin/users          : 全ユーザー手数料サマリー（admin）
- GET  /api/billing/admin/monthly-entries: 月次明細一覧（admin）
- GET  /api/billing/admin/monthly-summary: 月次集計（admin）
- POST /api/billing/admin/{user_id}/refund: リファンド処理（admin）
- GET  /api/billing/admin/export-csv     : CSV エクスポート（admin）
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import User
from app.database import get_db

from .schemas import (
    AdminFeeMonthlyEntry,
    AdminFeeRefundRequest,
    AdminFeeRefundResponse,
    AdminFeeUserRow,
    AdminMonthlyAggregate,
    BatchResult,
    FeeCalculationResponse,
    FeeConfigResponse,
    FeeSummaryResponse,
)
from .service import BillingService, BillingServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_billing_service = BillingService()


@router.get("/fees", response_model=list[FeeCalculationResponse])
async def get_fees(
    user_id: int,
    period: Optional[str] = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_viewer),
) -> list[FeeCalculationResponse]:
    """
    ユーザーの手数料履歴を返す。

    Args:
        user_id: 対象ユーザー ID
        period: 期間種別フィルタ（'daily' or 'monthly'、省略可）

    Returns:
        FeeCalculationResponse のリスト
    """
    try:
        calculations = _billing_service.get_user_fee_history(
            db=db,
            user_id=user_id,
            period_type=period,
        )
        return [FeeCalculationResponse.model_validate(c) for c in calculations]
    except Exception as exc:
        logger.error("Failed to get fee history for user_id=%d: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve fee history",
        ) from exc


@router.get("/summary", response_model=FeeSummaryResponse)
async def get_summary(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_viewer),
) -> FeeSummaryResponse:
    """
    ユーザーの手数料累計サマリーを返す。

    Args:
        user_id: 対象ユーザー ID

    Returns:
        FeeSummaryResponse
    """
    try:
        return _billing_service.get_user_fee_summary(db=db, user_id=user_id)
    except Exception as exc:
        logger.error("Failed to get fee summary for user_id=%d: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve fee summary",
        ) from exc


@router.post("/batch/daily", response_model=BatchResult)
async def run_daily_batch(
    user_aum_map: dict[str, str],
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> BatchResult:
    """
    日次手数料バッチを実行する（管理者のみ）。

    リクエストボディ例:
        {"1": "10000.00", "2": "5000.00"}

    Args:
        user_aum_map: {user_id(str): aum(str)} の辞書

    Returns:
        BatchResult
    """
    # str キー/値 → int キー/Decimal 値 に変換
    parsed_map: dict[int, Decimal] = {}
    for user_id_str, aum_str in user_aum_map.items():
        try:
            uid = int(user_id_str)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid user_id key: '{user_id_str}'",
            ) from exc
        try:
            aum = Decimal(aum_str)
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid AUM value for user_id={uid}: '{aum_str}'",
            ) from exc
        parsed_map[uid] = aum

    try:
        result = _billing_service.run_daily_fee_batch(db=db, user_aum_map=parsed_map)
        return result
    except BillingServiceError as exc:
        logger.error("Daily batch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("/config", response_model=FeeConfigResponse)
async def get_config(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_viewer),
) -> FeeConfigResponse:
    """
    現在の手数料設定を返す。

    Returns:
        FeeConfigResponse
    """
    try:
        config = _billing_service.get_active_fee_config(db=db)
        return FeeConfigResponse.model_validate(config)
    except Exception as exc:
        logger.error("Failed to get fee config: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve fee config",
        ) from exc


# ── Admin endpoints (F-12) ──────────────────────────────────────────────────


@router.get("/admin/users", response_model=list[AdminFeeUserRow])
async def admin_list_users_fees(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[AdminFeeUserRow]:
    """全ユーザーの手数料累計サマリーを返す（管理者のみ）。"""
    try:
        return _billing_service.get_all_users_fee_overview(db=db)
    except Exception as exc:
        logger.error("Failed to get admin user fee overview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user fee overview",
        ) from exc


@router.get("/admin/monthly-entries", response_model=list[AdminFeeMonthlyEntry])
async def admin_list_monthly_entries(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="対象月 YYYY-MM"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[AdminFeeMonthlyEntry]:
    """指定月の手数料明細を返す（管理者のみ）。"""
    try:
        return _billing_service.get_monthly_fee_entries(db=db, month=month)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed to get monthly entries for month=%s: %s", month, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monthly entries",
        ) from exc


@router.get("/admin/monthly-summary", response_model=AdminMonthlyAggregate)
async def admin_get_monthly_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="対象月 YYYY-MM"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AdminMonthlyAggregate:
    """指定月の手数料集計を返す（管理者のみ）。"""
    try:
        return _billing_service.get_monthly_aggregate(db=db, month=month)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed to get monthly summary for month=%s: %s", month, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monthly summary",
        ) from exc


@router.post("/admin/{user_id}/refund", response_model=AdminFeeRefundResponse)
async def admin_create_refund(
    req: AdminFeeRefundRequest,
    user_id: int = Path(..., description="対象ユーザー ID"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AdminFeeRefundResponse:
    """指定ユーザーへのリファンドを記録する（管理者のみ）。"""
    if req.amount <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount must be positive",
        )
    try:
        return _billing_service.create_refund(
            db=db,
            user_id=user_id,
            amount=req.amount,
            reason=req.reason,
        )
    except Exception as exc:
        from .service import BillingServiceError

        if isinstance(exc, BillingServiceError) and "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        logger.error("Failed to create refund for user_id=%d: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create refund",
        ) from exc


@router.get("/admin/export-csv")
async def admin_export_csv(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="対象月 YYYY-MM"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> Response:
    """指定月の手数料明細を CSV でエクスポートする（管理者のみ）。"""
    try:
        csv_content = _billing_service.export_monthly_csv(db=db, month=month)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="fees_{month}.csv"'},
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed to export CSV for month=%s: %s", month, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export CSV",
        ) from exc
