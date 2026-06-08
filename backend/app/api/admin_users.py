# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/api/admin_users.py
"""管理者向けユーザー運用状況 API。

GET   /api/admin/users              - 全ユーザー一覧（viewer ロール、運用データ付き）
POST  /api/admin/users/{id}/pause   - ユーザー運用停止（is_active = False）
POST  /api/admin/users/{id}/resume  - ユーザー運用再開（is_active = True）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.models import AIDecision
from app.auth.dependencies import require_admin
from app.auth.models import User, UserRole
from app.database import get_db
from app.portfolio.models import PortfolioSnapshot
from app.transactions.models import Transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


# ─── Response schemas ─────────────────────────────────────────────────────────


class PositionItem(BaseModel):
    asset: str
    supplied: float
    borrowed: float
    usdValue: float


class HFPoint(BaseModel):
    date: str
    hf: float


class RecentTrade(BaseModel):
    id: str
    type: str
    asset: str
    amount: float
    timestamp: str


class RecentDecision(BaseModel):
    id: str
    action: str
    confidence: int
    timestamp: str


class AdminUserDetail(BaseModel):
    id: str
    address: str
    registeredAt: str
    aum: float
    lastActivity: str
    riskMode: str
    status: str  # NORMAL | WARNING | DANGER
    isPaused: bool
    positions: List[PositionItem]
    healthFactor: float
    hfHistory: List[HFPoint]
    recentTrades: List[RecentTrade]
    recentDecisions: List[RecentDecision]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _hf_status(hf: float) -> str:
    if hf < 1.6:
        return "DANGER"
    if hf < 2.0:
        return "WARNING"
    return "NORMAL"


def _parse_positions(positions_json: Any) -> List[PositionItem]:
    if not positions_json or not isinstance(positions_json, list):
        return []
    result: List[PositionItem] = []
    for p in positions_json:
        if not isinstance(p, dict):
            continue
        result.append(
            PositionItem(
                asset=str(p.get("asset", "")),
                supplied=float(p.get("supplied", 0) or 0),
                borrowed=float(p.get("borrowed", 0) or 0),
                usdValue=float(p.get("usdValue", p.get("usd_value", 0)) or 0),
            )
        )
    return result


def _build_hf_history(snapshots: List[PortfolioSnapshot]) -> List[HFPoint]:
    """スナップショット（recorded_at DESC）から日別1点のHF履歴を古→新で返す。"""
    seen_dates: set[str] = set()
    points: List[HFPoint] = []
    for snap in snapshots:
        if snap.health_factor is None:
            continue
        d = snap.recorded_at.strftime("%Y-%m-%d")
        if d in seen_dates:
            continue
        seen_dates.add(d)
        points.append(HFPoint(date=d, hf=float(snap.health_factor)))
    points.reverse()
    return points


def _build_detail(
    user: User,
    latest_snap: Optional[PortfolioSnapshot],
    hf_snaps: List[PortfolioSnapshot],
    trades: List[Transaction],
    decisions: List[AIDecision],
) -> AdminUserDetail:
    aum = float(latest_snap.total_value_usd) if latest_snap else 0.0
    hf = (
        float(latest_snap.health_factor)
        if (latest_snap and latest_snap.health_factor is not None)
        else 0.0
    )

    timestamps: List[datetime] = [user.created_at]
    if trades:
        timestamps.append(trades[0].created_at)
    if decisions:
        timestamps.append(decisions[0].created_at)
    last_activity = max(timestamps)

    return AdminUserDetail(
        id=str(user.id),
        address=user.wallet_address or "",
        registeredAt=user.created_at.isoformat(),
        aum=aum,
        lastActivity=last_activity.isoformat(),
        riskMode=user.risk_mode or "conservative",
        status=_hf_status(hf),
        isPaused=not user.is_active,
        positions=_parse_positions(latest_snap.positions_json if latest_snap else None),
        healthFactor=hf,
        hfHistory=_build_hf_history(hf_snaps),
        recentTrades=[
            RecentTrade(
                id=str(t.id),
                type=t.operation,
                asset=t.asset,
                amount=float(t.amount_usd),
                timestamp=t.created_at.isoformat(),
            )
            for t in trades
        ],
        recentDecisions=[
            RecentDecision(
                id=str(d.id),
                action=d.action,
                confidence=d.confidence,
                timestamp=d.created_at.isoformat(),
            )
            for d in decisions
        ],
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=List[AdminUserDetail], summary="管理者: ユーザー運用一覧")
def list_admin_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[AdminUserDetail]:
    """全 viewer ユーザーの運用状況（ポートフォリオ・HF・取引・AI判定）を返す。"""
    users = (
        db.query(User)
        .filter(User.role == UserRole.VIEWER.value)
        .order_by(User.created_at.desc())
        .all()
    )

    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    result: List[AdminUserDetail] = []

    for user in users:
        latest_snap = (
            db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.user_id == user.id)
            .order_by(PortfolioSnapshot.recorded_at.desc())
            .first()
        )
        hf_snaps = (
            db.query(PortfolioSnapshot)
            .filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.recorded_at >= since_7d,
            )
            .order_by(PortfolioSnapshot.recorded_at.desc())
            .limit(50)
            .all()
        )
        trades = (
            db.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .order_by(Transaction.created_at.desc())
            .limit(5)
            .all()
        )
        decisions = (
            db.query(AIDecision)
            .filter(AIDecision.user_id == user.id)
            .order_by(AIDecision.created_at.desc())
            .limit(5)
            .all()
        )
        result.append(_build_detail(user, latest_snap, hf_snaps, trades, decisions))

    return result


@router.post("/{user_id}/pause", summary="管理者: ユーザー運用停止")
def pause_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """指定ユーザーの自動取引を停止する（is_active = False）。"""
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.VIEWER.value).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    db.commit()
    logger.info("Admin %s paused user %d", admin.email, user_id)
    return {"message": "paused", "user_id": user_id, "isPaused": True}


@router.post("/{user_id}/resume", summary="管理者: ユーザー運用再開")
def resume_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """指定ユーザーの自動取引を再開する（is_active = True）。"""
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.VIEWER.value).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = True
    db.commit()
    logger.info("Admin %s resumed user %d", admin.email, user_id)
    return {"message": "resumed", "user_id": user_id, "isPaused": False}
