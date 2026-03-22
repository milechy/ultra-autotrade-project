# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/router.py
"""提案API ルーター定義。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin, require_viewer
from app.auth.models import User
from app.database import get_db

from .models import Proposal
from .schemas import ProposalCreate, ProposalListResponse, ProposalResponse

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def _expire_old_proposals(db: Session, user_id: int) -> None:
    """期限切れのpending提案をexpiredに更新する。"""
    now = datetime.now(timezone.utc)
    stmt = select(Proposal).where(
        Proposal.user_id == user_id,
        Proposal.status == "pending",
        Proposal.expires_at < now,
    )
    expired = db.scalars(stmt).all()
    for p in expired:
        p.status = "expired"
    if expired:
        db.commit()


@router.get("/pending", response_model=ProposalListResponse, summary="保留中の提案リスト")
def list_pending_proposals(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    """自分の保留中（pending）提案リストを返す。"""
    _expire_old_proposals(db, current_user.id)
    stmt = select(Proposal).where(
        Proposal.user_id == current_user.id,
        Proposal.status == "pending",
    ).order_by(Proposal.created_at.desc())
    items = db.scalars(stmt).all()
    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in items],
        total=len(items),
    )


@router.get("/history", response_model=ProposalListResponse, summary="提案履歴")
def list_proposal_history(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    """承認・拒否・実行済みの提案履歴を返す。"""
    stmt = select(Proposal).where(
        Proposal.user_id == current_user.id,
        Proposal.status.in_(["approved", "rejected", "executed"]),
    ).order_by(Proposal.created_at.desc())
    items = db.scalars(stmt).all()
    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in items],
        total=len(items),
    )


@router.post("/{proposal_id}/approve", response_model=ProposalResponse, summary="提案承認")
def approve_proposal(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を承認する（本人のみ）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve proposal with status '{proposal.status}'",
        )
    proposal.status = "approved"
    proposal.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse, summary="提案拒否")
def reject_proposal(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を拒否する（本人のみ）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject proposal with status '{proposal.status}'",
        )
    proposal.status = "rejected"
    proposal.rejected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}", response_model=ProposalResponse, summary="提案詳細")
def get_proposal(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """指定IDの提案詳細を返す（本人またはadmin）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None or (
        proposal.user_id != current_user.id and not current_user.is_admin
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return ProposalResponse.model_validate(proposal)


@router.post(
    "",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提案作成",
)
def create_proposal(
    request: ProposalCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を作成する（内部呼び出し用）。"""
    expires_at = request.expires_at or (datetime.now(timezone.utc) + timedelta(hours=24))
    proposal = Proposal(
        user_id=request.user_id,
        ai_decision_id=request.ai_decision_id,
        operation=request.operation,
        asset=request.asset,
        amount=request.amount,
        amount_usd=request.amount_usd,
        reason=request.reason,
        expected_hf_after=request.expected_hf_after,
        estimated_gas_usd=request.estimated_gas_usd,
        expires_at=expires_at,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)
