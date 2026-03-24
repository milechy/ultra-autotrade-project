# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/router.py
"""ポートフォリオ履歴API ルーター定義。"""

import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import User
from app.database import get_db

from .models import PortfolioSnapshot
from .schemas import (
    PortfolioCurrentResponse,
    PortfolioHistoryResponse,
    PortfolioLiveResponse,
    PortfolioSnapshotCreate,
    PortfolioSnapshotResponse,
)

# 30秒インメモリキャッシュ: {cache_key: (timestamp, data)}
_live_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 30

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioLiveResponse, summary="ライブAaveポートフォリオデータ")
def get_live_portfolio(
    chain: str = Query(
        default="arbitrum_sepolia", description="チェーン名 (arbitrum_sepolia など)"
    ),
    current_user: User = Depends(require_viewer),
) -> PortfolioLiveResponse:
    """Aave getUserAccountData() をリアルタイム取得して返す（30秒キャッシュ）。"""
    from app.aave.client import get_default_aave_client  # noqa: PLC0415

    cache_key = chain
    now_ts = time.monotonic()
    cached = _live_cache.get(cache_key)
    if cached is not None:
        ts, data = cached
        if now_ts - ts < _CACHE_TTL_SECONDS:
            return data

    wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")

    try:
        client = get_default_aave_client()
        account_data = client.get_account_data(wallet_address)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Aaveデータの取得に失敗しました: {exc}",
        ) from exc

    hf = account_data.health_factor
    hf_result: Optional[Decimal] = None if hf == Decimal("inf") or str(hf) == "Infinity" else hf

    response = PortfolioLiveResponse(
        total_supply_usd=account_data.total_collateral_usd,
        total_borrow_usd=account_data.total_debt_usd,
        health_factor=hf_result,
        net_worth_usd=account_data.total_collateral_usd - account_data.total_debt_usd,
        positions=[],
        chain=chain,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    _live_cache[cache_key] = (now_ts, response)
    return response


def _get_since(period: str) -> Optional[datetime]:
    """期間文字列から開始datetimeを返す。"""
    now = datetime.now(timezone.utc)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None  # "all"


@router.get("/current", response_model=PortfolioCurrentResponse, summary="現在のポートフォリオ")
def get_current_portfolio(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> PortfolioCurrentResponse:
    """最新のスナップショットを返す。データなし時は空レスポンス。"""
    stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == current_user.id)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .limit(1)
    )
    snapshot = db.scalars(stmt).first()
    if snapshot is None:
        return PortfolioCurrentResponse(user_id=current_user.id, has_data=False)

    return PortfolioCurrentResponse(
        id=snapshot.id,
        user_id=snapshot.user_id,
        total_value_usd=snapshot.total_value_usd,
        total_supply_usd=snapshot.total_supply_usd,
        total_borrow_usd=snapshot.total_borrow_usd,
        health_factor=snapshot.health_factor,
        positions_json=snapshot.positions_json,
        recorded_at=snapshot.recorded_at,
        has_data=True,
    )


@router.get("/history", response_model=PortfolioHistoryResponse, summary="資産推移履歴")
def get_portfolio_history(
    period: str = "30d",
    interval: str = "daily",
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> PortfolioHistoryResponse:
    """資産推移データを返す。period: 7d/30d/90d/all, interval: hourly/daily。"""
    if period not in ("7d", "30d", "90d", "all"):
        period = "30d"
    if interval not in ("hourly", "daily"):
        interval = "daily"
    since = _get_since(period)
    stmt = select(PortfolioSnapshot).where(PortfolioSnapshot.user_id == current_user.id)
    if since:
        stmt = stmt.where(PortfolioSnapshot.recorded_at >= since)
    stmt = stmt.order_by(PortfolioSnapshot.recorded_at.asc())
    items = db.scalars(stmt).all()
    return PortfolioHistoryResponse(
        items=[PortfolioSnapshotResponse.model_validate(s) for s in items],
        total=len(items),
        period=period,
        interval=interval,
    )


@router.post(
    "/snapshot",
    response_model=PortfolioSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="スナップショット記録",
)
def create_snapshot(
    request: PortfolioSnapshotCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortfolioSnapshotResponse:
    """ポートフォリオスナップショットを記録する（バッチジョブ用）。"""
    recorded_at = request.recorded_at or datetime.now(timezone.utc)
    snapshot = PortfolioSnapshot(
        user_id=request.user_id,
        total_value_usd=request.total_value_usd,
        total_supply_usd=request.total_supply_usd,
        total_borrow_usd=request.total_borrow_usd,
        health_factor=request.health_factor,
        positions_json=request.positions_json,
        recorded_at=recorded_at,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return PortfolioSnapshotResponse.model_validate(snapshot)
