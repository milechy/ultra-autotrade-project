# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/api/v1/fee_transfer.py
"""Fee transfer & allowance API endpoints (Lane R).

Asana 1215272587496967: on-chain fee transfer (FEE_TRANSFER_ENABLED gate)
Asana 1215273755294098: fee allowance approve UX (Privy / EIP-2612 permit)

Endpoints:
  GET  /api/v1/fees/transfer/allowance-status   user 自身の現在 allowance 確認
  GET  /api/v1/fees/transfer/permit-data        EIP-712 typed data 取得 (Privy 署名用)
  POST /api/v1/fees/transfer/submit-permit      署名済み permit を on-chain submit
  POST /api/v1/fees/transfer/execute            admin: fee_transaction に対して on-chain transfer 実行
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import User
from app.database import get_db
from app.fees.allowance_models import FeeAllowance
from app.fees.allowance_service import AllowanceService
from app.fees.models import FeeTransaction
from app.fees.transfer_service import FeeTransferService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fees/transfer", tags=["fee-transfer"])

_allowance_svc = AllowanceService()
_transfer_svc = FeeTransferService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AllowanceStatusResponse(BaseModel):
    user_wallet_addr: str
    current_allowance_usdc: str
    atoken_address: str
    fee_transfer_enabled: bool


class PermitDataResponse(BaseModel):
    domain: dict[str, object]
    types: dict[str, object]
    primary_type: str
    message: dict[str, object]
    atoken_address: str
    chain_id: int


class SubmitPermitRequest(BaseModel):
    user_wallet_addr: str = Field(..., description="permit owner アドレス (checksum)")
    allowance_limit_usdc: Decimal = Field(..., gt=0, description="上限 (USDC 単位)")
    deadline_ts: int = Field(..., gt=0, description="UNIX timestamp (permit 有効期限)")
    v: int = Field(..., ge=0, le=255)
    r: str = Field(..., description="r component (0x プレフィクス付き 32bytes hex)")
    s: str = Field(..., description="s component (0x プレフィクス付き 32bytes hex)")


class SubmitPermitResponse(BaseModel):
    tx_hash: str
    user_address: str
    operator_address: str
    allowance_limit_usdc: str
    deadline_ts: int
    db_record_id: int


class ExecuteTransferRequest(BaseModel):
    fee_tx_id: int = Field(..., description="fee_transactions.id")
    user_wallet_addr: str = Field(..., description="支払いユーザーの wallet アドレス")
    fee_amount_usdc: Decimal = Field(..., gt=0, description="送金額 (USDC 単位)")
    dry_run: bool = Field(default=False, description="True なら on-chain 送金しない")


class ExecuteTransferResponse(BaseModel):
    fee_tx_id: int
    tx_hash: str | None
    amount_usdc: str
    from_address: str
    enabled: bool
    dry_run: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/allowance-status",
    response_model=AllowanceStatusResponse,
    summary="現在の aBasUSDC allowance (user 自身)",
)
def get_allowance_status(
    user: User = Depends(require_active_user),
) -> AllowanceStatusResponse:
    """ログインユーザーの wallet に対する aBasUSDC allowance を確認する。"""
    if not user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ユーザーの wallet_address が未設定です。",
        )
    try:
        allowance = _transfer_svc.get_allowance(user.wallet_address)
    except Exception as exc:
        logger.warning("allowance 取得エラー: %s", exc)
        allowance = Decimal("0")

    from app.fees.transfer_service import _get_atoken_address, _is_transfer_enabled

    return AllowanceStatusResponse(
        user_wallet_addr=user.wallet_address,
        current_allowance_usdc=str(allowance),
        atoken_address=_get_atoken_address(),
        fee_transfer_enabled=_is_transfer_enabled(),
    )


@router.get(
    "/permit-data",
    response_model=PermitDataResponse,
    summary="EIP-712 permit typed data 取得 (Privy 署名用)",
)
def get_permit_data(
    user: User = Depends(require_active_user),
    allowance_limit_usdc: Decimal = Query(..., gt=0, description="上限 USDC"),
    deadline_ts: int = Query(..., gt=0, description="UNIX timestamp"),
) -> PermitDataResponse:
    """EIP-712 typed data を返す。frontend が Privy で署名し submit-permit へ渡す。"""
    if not user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ユーザーの wallet_address が未設定です。",
        )
    try:
        data = _allowance_svc.build_permit_typed_data(
            user_address=user.wallet_address,
            allowance_limit_usdc=allowance_limit_usdc,
            deadline_ts=deadline_ts,
        )
    except Exception as exc:
        logger.error("permit typed data 構築エラー: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"permit typed data 構築に失敗しました: {exc}",
        ) from exc

    return PermitDataResponse(
        domain=data.domain,
        types=data.types,
        primary_type=data.primary_type,
        message=data.message,
        atoken_address=data.atoken_address,
        chain_id=data.chain_id,
    )


@router.post(
    "/submit-permit",
    response_model=SubmitPermitResponse,
    summary="署名済み permit を on-chain submit (operator が gas 負担)",
)
def submit_permit(
    payload: SubmitPermitRequest,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> SubmitPermitResponse:
    """Privy で sign した permit を operator が on-chain submit し allowance を設定する。"""
    if not user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ユーザーの wallet_address が未設定です。",
        )
    if user.wallet_address.lower() != payload.user_wallet_addr.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_wallet_addr がログインユーザーと一致しません。",
        )

    record = FeeAllowance(
        user_id=user.id,
        user_wallet_addr=payload.user_wallet_addr,
        allowance_limit=payload.allowance_limit_usdc,
        permit_deadline=datetime.fromtimestamp(payload.deadline_ts, tz=timezone.utc),
        status="pending",
    )
    db.add(record)
    db.flush()
    record_id = record.id

    try:
        result = _allowance_svc.submit_permit(
            user_address=payload.user_wallet_addr,
            allowance_limit_usdc=payload.allowance_limit_usdc,
            deadline_ts=payload.deadline_ts,
            v=payload.v,
            r=payload.r,
            s=payload.s,
        )
    except Exception as exc:
        record.status = "expired"
        db.commit()
        logger.error("permit submit 失敗: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"permit on-chain submit 失敗: {exc}",
        ) from exc

    record.tx_hash_permit = result.tx_hash
    record.status = "confirmed"
    record.updated_at = datetime.now(timezone.utc)
    db.commit()

    return SubmitPermitResponse(
        tx_hash=result.tx_hash,
        user_address=result.user_address,
        operator_address=result.operator_address,
        allowance_limit_usdc=str(result.allowance_limit_usdc),
        deadline_ts=result.deadline_ts,
        db_record_id=record_id,
    )


@router.post(
    "/execute",
    response_model=ExecuteTransferResponse,
    summary="fee_transaction に対して on-chain fee transfer 実行 (admin)",
    dependencies=[Depends(require_admin)],
)
def execute_fee_transfer(
    payload: ExecuteTransferRequest,
    db: Session = Depends(get_db),
) -> ExecuteTransferResponse:
    """指定した fee_transaction の fee を on-chain で operator に送金する。

    FEE_TRANSFER_ENABLED=false のときは no-op で返す (enabled=false)。
    dry_run=true のときは allowance 確認のみ行い送金しない。
    """
    fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.id == payload.fee_tx_id))
    if fee_tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fee_transaction id={payload.fee_tx_id} が存在しません。",
        )
    if fee_tx.on_chain_tx_hash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"fee_transaction id={payload.fee_tx_id} は既に送金済みです (tx={fee_tx.on_chain_tx_hash})。",
        )

    try:
        result = _transfer_svc.transfer_fee(
            user_address=payload.user_wallet_addr,
            fee_amount_usdc=payload.fee_amount_usdc,
            fee_tx_db_id=payload.fee_tx_id,
            dry_run=payload.dry_run,
        )
    except Exception as exc:
        logger.error("fee transfer 実行エラー fee_tx_id=%d: %s", payload.fee_tx_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"fee transfer 失敗: {exc}",
        ) from exc

    if result.tx_hash and not payload.dry_run:
        fee_tx.on_chain_tx_hash = result.tx_hash
        db.commit()

    return ExecuteTransferResponse(
        fee_tx_id=payload.fee_tx_id,
        tx_hash=result.tx_hash,
        amount_usdc=str(result.amount_usdc),
        from_address=result.from_address,
        enabled=result.enabled,
        dry_run=result.dry_run,
    )
