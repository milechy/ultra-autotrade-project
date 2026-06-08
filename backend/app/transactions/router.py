# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/transactions/router.py
"""取引履歴API ルーター定義。"""

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin, require_editor, require_viewer
from app.auth.models import User
from app.database import get_db
from app.proposals.models import Proposal

from .models import Transaction
from .schemas import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionStatsResponse,
)

_JST = ZoneInfo("Asia/Tokyo")

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
admin_router = APIRouter(prefix="/api/admin/transactions", tags=["admin-transactions"])


@router.get("/stats", response_model=TransactionStatsResponse, summary="取引統計")
def get_transaction_stats(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> TransactionStatsResponse:
    """自分の累計取引統計を返す。"""
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    all_txs = db.scalars(stmt).all()
    success_txs = [t for t in all_txs if t.status == "success"]
    total_amount_usd = sum((t.amount_usd for t in all_txs), Decimal("0"))
    total_gas = Decimal("0")
    for t in all_txs:
        if t.gas_used is not None and t.gas_price_gwei is not None:
            total_gas += t.gas_used * t.gas_price_gwei / Decimal("1000000000")
    return TransactionStatsResponse(
        total_count=len(all_txs),
        success_count=len(success_txs),
        total_amount_usd=total_amount_usd,
        total_gas_usd=total_gas,
    )


@router.get("", response_model=TransactionListResponse, summary="取引履歴リスト")
def list_transactions(
    limit: int = 20,
    offset: int = 0,
    operation: Optional[str] = None,
    asset: Optional[str] = None,
    tx_status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    chain: Optional[str] = None,
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    """自分の取引履歴リストを返す。"""
    limit = min(limit, 100)
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    if operation:
        stmt = stmt.where(Transaction.operation == operation)
    if asset:
        stmt = stmt.where(Transaction.asset == asset)
    if tx_status:
        stmt = stmt.where(Transaction.status == tx_status)
    if date_from:
        stmt = stmt.where(Transaction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.created_at <= date_to)
    if chain:
        stmt = stmt.where(Transaction.chain == chain)
    total = len(db.scalars(stmt).all())
    stmt = stmt.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
    items = db.scalars(stmt).all()
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export", summary="取引一覧 CSV エクスポート")
def export_transactions_csv(
    year: Optional[int] = Query(None, description="絞り込む年 (例: 2026)。省略時は全件"),
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> Response:
    """実行済み提案 (status='executed') を CSV 形式でエクスポートする。

    CSV カラム: 実行日時, 操作, 資産, 数量, USD金額, 手数料(USD), TxHash
    - 実行日時: JST (UTC+9) 形式 YYYY/MM/DD HH:MM:SS
    - 操作: SUPPLY / WITHDRAW / BORROW / REPAY
    - 数量: トークン数量 (Decimal)
    - USD金額: 実行時の USD 換算額
    - 手数料(USD): fee_amount。NULL の場合は 0
    """
    stmt = select(Proposal).where(
        Proposal.user_id == current_user.id,
        Proposal.status == "executed",
        Proposal.executed_at.is_not(None),
    )
    if year is not None:
        stmt = stmt.where(func.extract("year", Proposal.executed_at) == year)
    stmt = stmt.order_by(Proposal.executed_at.asc())
    proposals = db.scalars(stmt).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["実行日時", "操作", "資産", "数量", "USD金額", "手数料(USD)", "TxHash"])

    for p in proposals:
        if p.executed_at is None:
            continue
        dt = p.executed_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        executed_jst = dt.astimezone(_JST)
        timestamp = executed_jst.strftime("%Y/%m/%d %H:%M:%S")
        fee = str(p.fee_amount) if p.fee_amount is not None else "0"
        writer.writerow(
            [timestamp, p.operation, p.asset, str(p.amount), str(p.amount_usd), fee, p.tx_hash or ""]
        )

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM付きUTF-8 (Excel対応)
    year_suffix = f"_{year}" if year else ""
    filename = f"transactions{year_suffix}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{transaction_id}", response_model=TransactionResponse, summary="取引詳細")
def get_transaction(
    transaction_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """指定IDの取引詳細を返す（本人またはadminのみ）。"""
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    tx = db.scalars(stmt).first()
    if tx is None or (tx.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return TransactionResponse.model_validate(tx)


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="取引記録作成",
)
def create_transaction(
    request: TransactionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """取引記録を作成する（内部呼び出し用）。"""
    tx = Transaction(**request.model_dump())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return TransactionResponse.model_validate(tx)


@admin_router.get("", response_model=TransactionListResponse, summary="全取引履歴（管理者）")
def admin_list_transactions(
    limit: int = 20,
    offset: int = 0,
    user_id: Optional[int] = None,
    wallet_address: Optional[str] = None,
    operation: Optional[str] = None,
    asset: Optional[str] = None,
    tx_status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    """全ユーザーの取引履歴リストを返す（editor以上）。"""
    limit = min(limit, 100)
    stmt = select(Transaction)
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    if wallet_address:
        stmt = stmt.where(Transaction.wallet_address.ilike(f"%{wallet_address}%"))
    if operation:
        stmt = stmt.where(Transaction.operation == operation)
    if asset:
        stmt = stmt.where(Transaction.asset == asset)
    if tx_status:
        stmt = stmt.where(Transaction.status == tx_status)
    if date_from:
        stmt = stmt.where(Transaction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.created_at <= date_to)
    total = len(db.scalars(stmt).all())
    stmt = stmt.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
    items = db.scalars(stmt).all()
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )
