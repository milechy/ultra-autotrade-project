# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/allocation_service.py
"""
資金割り振りサービス層。

CRUD 操作と Aave ポジションを使ったテスター別パフォーマンス按分計算を提供する。
金融計算は Decimal 型のみ使用（float 禁止）。
"""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.aave.client import get_default_aave_client
from app.auth.models import User

from .allocation_models import FundAllocation
from .allocation_schemas import (
    AllocationCreateRequest,
    AllocationResponse,
    AllocationUpdateRequest,
    PerformanceSummary,
    TesterPerformance,
)

logger = logging.getLogger(__name__)

# HF が Infinity（ポジションなし）の場合の表示値
_HF_INFINITY_DISPLAY = Decimal("999.0")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_allocation(
    db: Session,
    partner_id: int,
    request: AllocationCreateRequest,
) -> AllocationResponse:
    """新しい資金割り振りレコードを作成する。"""
    now = datetime.now(timezone.utc)
    allocation = FundAllocation(
        partner_id=partner_id,
        tester_name=request.tester_name,
        allocated_amount_usd=request.allocated_amount_usd,
        status="active",
        allocated_at=now,
        notes=request.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(allocation)
    db.commit()
    db.refresh(allocation)
    return AllocationResponse.model_validate(allocation)


def get_allocations(
    db: Session,
    partner_id: int,
    status: Optional[str] = "active",
) -> list[AllocationResponse]:
    """
    パートナーの資金割り振り一覧を返す。

    Args:
        db: DB セッション
        partner_id: パートナー ID
        status: フィルタするステータス。None の場合は全件返す。
    """
    query = db.query(FundAllocation).filter(FundAllocation.partner_id == partner_id)
    if status is not None:
        query = query.filter(FundAllocation.status == status)
    rows = query.order_by(FundAllocation.allocated_at.desc()).all()
    return [AllocationResponse.model_validate(r) for r in rows]


def get_allocation_by_id(
    db: Session,
    allocation_id: int,
    partner_id: int,
) -> Optional[FundAllocation]:
    """ID でレコードを取得する。partner_id で所有確認を行う。"""
    return (
        db.query(FundAllocation)
        .filter(
            FundAllocation.id == allocation_id,
            FundAllocation.partner_id == partner_id,
        )
        .first()
    )


def update_allocation(
    db: Session,
    allocation_id: int,
    partner_id: int,
    request: AllocationUpdateRequest,
) -> Optional[AllocationResponse]:
    """
    資金割り振りを更新する。

    Returns:
        更新後のレスポンス。該当レコードが存在しない場合は None。
    """
    allocation = get_allocation_by_id(db, allocation_id, partner_id)
    if allocation is None:
        return None

    if request.tester_name is not None:
        allocation.tester_name = request.tester_name
    if request.allocated_amount_usd is not None:
        allocation.allocated_amount_usd = request.allocated_amount_usd
    if request.status is not None:
        allocation.status = request.status
        if request.status == "withdrawn" and allocation.withdrawn_at is None:
            allocation.withdrawn_at = datetime.now(timezone.utc)
    if request.notes is not None:
        allocation.notes = request.notes

    allocation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(allocation)
    return AllocationResponse.model_validate(allocation)


def delete_allocation(
    db: Session,
    allocation_id: int,
    partner_id: int,
) -> bool:
    """
    資金割り振りを削除する。

    Returns:
        削除成功なら True、対象なし（または所有権なし）なら False。
    """
    allocation = get_allocation_by_id(db, allocation_id, partner_id)
    if allocation is None:
        return False
    db.delete(allocation)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# パフォーマンス按分計算
# ---------------------------------------------------------------------------


def _get_wallet_address(partner: User) -> str:
    """
    パートナーの Aave ウォレットアドレスを取得する。

    users.wallet_address が設定されていれば優先、なければ
    AAVE_WALLET_ADDRESS 環境変数にフォールバックする。
    """
    if partner.wallet_address:
        return partner.wallet_address
    return os.getenv("AAVE_WALLET_ADDRESS", "")


def get_performance(
    db: Session,
    partner: User,
) -> PerformanceSummary:
    """
    パートナーの Aave ポジションをテスター別に按分してパフォーマンスを返す。

    按分ロジック:
        ratio = allocation.allocated_amount_usd / total_allocated
        current_value = ratio * total_supply_usd (Aave total_collateral_usd)
        pnl_usd = current_value - allocated_amount_usd
        pnl_percentage = pnl_usd / allocated_amount_usd * 100 （既に % 換算済み）

    HF が Infinity（ポジションなし）の場合は Decimal("999.0") に丸める。
    """
    # アクティブな割り振りのみ対象
    allocations = (
        db.query(FundAllocation)
        .filter(
            FundAllocation.partner_id == partner.id,
            FundAllocation.status == "active",
        )
        .all()
    )

    total_allocated = sum(
        (Decimal(str(a.allocated_amount_usd)) for a in allocations),
        Decimal("0"),
    )

    # Aave ポジション取得
    wallet_addr = _get_wallet_address(partner)
    aave_client = get_default_aave_client()
    try:
        account_data = aave_client.get_account_data(wallet_addr)
        total_supply = Decimal(str(account_data.total_collateral_usd))
        raw_hf = Decimal(str(account_data.health_factor))
    except Exception:
        logger.exception("[allocation_service] Aave get_account_data failed; using zeros")
        total_supply = Decimal("0")
        raw_hf = _HF_INFINITY_DISPLAY

    # HF Infinity 丸め（既存パターン踏襲）
    try:
        hf_display = raw_hf if raw_hf.is_finite() else _HF_INFINITY_DISPLAY
    except Exception:
        hf_display = _HF_INFINITY_DISPLAY

    # テスター別按分計算
    testers: list[TesterPerformance] = []
    for alloc in allocations:
        allocated = Decimal(str(alloc.allocated_amount_usd))

        if total_allocated > Decimal("0"):
            ratio = (allocated / total_allocated).quantize(Decimal("0.000001"))
        else:
            ratio = Decimal("0")

        current_value = (ratio * total_supply).quantize(Decimal("0.000001"))
        pnl_usd = (current_value - allocated).quantize(Decimal("0.000001"))

        if allocated > Decimal("0"):
            pnl_pct = (pnl_usd / allocated * Decimal("100")).quantize(Decimal("0.0001"))
        else:
            pnl_pct = Decimal("0")

        testers.append(
            TesterPerformance(
                allocation_id=alloc.id,
                tester_name=alloc.tester_name,
                allocated_amount_usd=allocated,
                current_value_usd=current_value,
                pnl_usd=pnl_usd,
                pnl_percentage=pnl_pct,
                allocation_ratio=ratio,
            )
        )

    return PerformanceSummary(
        total_allocated_usd=total_allocated,
        total_supply_usd=total_supply,
        health_factor=hf_display,
        testers=testers,
    )
