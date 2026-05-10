# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/allocation_router.py
"""
資金割り振り API ルーター。

prefix "/api/partner" は main.py の include_router で付与される。

エンドポイント一覧:
    GET  /allocations           — 一覧（active のみデフォルト）
    POST /allocations           — 廃止 (410 Gone)
    PUT  /allocations/{id}      — 廃止 (410 Gone)
    DELETE /allocations/{id}    — 廃止 (410 Gone)
    GET  /performance           — テスター別パフォーマンス按分

権限: partner または admin（require_partner 依存）
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_partner
from app.auth.models import User
from app.database import get_db

from . import allocation_service as service
from .allocation_schemas import (
    AllocationResponse,
    PerformanceSummary,
)

router = APIRouter(tags=["partner-allocations"])


@router.get(
    "/allocations",
    response_model=list[AllocationResponse],
    summary="資金割り振り一覧",
)
def list_allocations(
    status: Optional[str] = Query(
        default="active", description="ステータスフィルタ（active/withdrawn/null=全件）"
    ),
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> list[AllocationResponse]:
    """パートナー配下の資金割り振り一覧を返す。デフォルトは active のみ。"""
    return service.get_allocations(db, current_user.id, status=status)


@router.post(
    "/allocations",
    status_code=status.HTTP_410_GONE,
    summary="資金割り振り作成（廃止）",
)
def create_allocation(
    current_user: User = Depends(require_partner),
) -> None:
    raise HTTPException(status_code=410, detail="この機能は廃止されました")


@router.put(
    "/allocations/{allocation_id}",
    status_code=status.HTTP_410_GONE,
    summary="資金割り振り更新（廃止）",
)
def update_allocation(
    allocation_id: int,
    current_user: User = Depends(require_partner),
) -> None:
    raise HTTPException(status_code=410, detail="この機能は廃止されました")


@router.delete(
    "/allocations/{allocation_id}",
    status_code=status.HTTP_410_GONE,
    summary="資金割り振り削除（廃止）",
)
def delete_allocation(
    allocation_id: int,
    current_user: User = Depends(require_partner),
) -> None:
    raise HTTPException(status_code=410, detail="この機能は廃止されました")


@router.get(
    "/performance",
    response_model=PerformanceSummary,
    summary="テスター別パフォーマンス按分",
)
def get_performance(
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> PerformanceSummary:
    """Aave ポジションをテスター別に按分してパフォーマンスを返す。"""
    return service.get_performance(db, current_user)
