# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/allocation_router.py
"""
資金割り振り API ルーター。

prefix "/api/partner" は main.py の include_router で付与される。

エンドポイント一覧:
    GET  /allocations           — 一覧（active のみデフォルト）
    POST /allocations           — 新規作成
    PUT  /allocations/{id}      — 更新
    DELETE /allocations/{id}    — 削除
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
    AllocationCreateRequest,
    AllocationResponse,
    AllocationUpdateRequest,
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
    response_model=AllocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="資金割り振り作成",
)
def create_allocation(
    body: AllocationCreateRequest,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> AllocationResponse:
    """新しい資金割り振りレコードを作成する。"""
    return service.create_allocation(db, current_user.id, body)


@router.put(
    "/allocations/{allocation_id}",
    response_model=AllocationResponse,
    summary="資金割り振り更新",
)
def update_allocation(
    allocation_id: int,
    body: AllocationUpdateRequest,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> AllocationResponse:
    """資金割り振りを更新する。対象が存在しない場合は 404。"""
    result = service.update_allocation(db, allocation_id, current_user.id, body)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation {allocation_id} not found",
        )
    return result


@router.delete(
    "/allocations/{allocation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="資金割り振り削除",
)
def delete_allocation(
    allocation_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> None:
    """資金割り振りを削除する。対象が存在しない場合は 404。"""
    deleted = service.delete_allocation(db, allocation_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation {allocation_id} not found",
        )


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
