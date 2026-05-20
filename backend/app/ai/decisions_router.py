# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/decisions_router.py
"""AI判定履歴API ルーター定義。"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_editor, require_viewer
from app.auth.models import User
from app.database import get_db

from .decisions_schemas import AIDecisionCreate, AIDecisionListResponse, AIDecisionResponse
from .models import AIDecision

router = APIRouter(prefix="/api/ai/decisions", tags=["ai-decisions"])


@router.get("/latest", response_model=AIDecisionResponse, summary="最新AI判定取得")
def get_latest_decision(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """最新の判定結果1件を返す。"""
    stmt = select(AIDecision).order_by(AIDecision.created_at.desc()).limit(1)
    decision = db.scalars(stmt).first()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No decisions found")
    return AIDecisionResponse.model_validate(decision)


@router.get("", response_model=AIDecisionListResponse, summary="AI判定履歴リスト")
def list_decisions(
    limit: int = 20,
    offset: int = 0,
    action: Optional[str] = None,
    min_confidence: Optional[int] = None,
    max_confidence: Optional[int] = None,
    agreed: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> AIDecisionListResponse:
    """判定履歴リストを返す（ページネーション・フィルタ付き）。"""
    limit = min(limit, 100)
    stmt = select(AIDecision)
    if action:
        stmt = stmt.where(AIDecision.action == action)
    if min_confidence is not None:
        stmt = stmt.where(AIDecision.confidence >= min_confidence)
    if max_confidence is not None:
        stmt = stmt.where(AIDecision.confidence <= max_confidence)
    if agreed is not None:
        stmt = stmt.where(AIDecision.agreed == agreed)
    if date_from:
        stmt = stmt.where(AIDecision.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AIDecision.created_at <= date_to)
    total_items = db.scalars(stmt).all()
    total = len(total_items)
    stmt = stmt.order_by(AIDecision.created_at.desc()).offset(offset).limit(limit)
    items = db.scalars(stmt).all()
    return AIDecisionListResponse(
        items=[AIDecisionResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{decision_id}", response_model=AIDecisionResponse, summary="AI判定詳細")
def get_decision(
    decision_id: int,
    current_user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """指定IDの判定詳細を返す。"""
    stmt = select(AIDecision).where(AIDecision.id == decision_id)
    decision = db.scalars(stmt).first()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return AIDecisionResponse.model_validate(decision)


@router.post(
    "",
    response_model=AIDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="AI判定記録",
)
def create_decision(
    request: AIDecisionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """判定結果を記録する（内部呼び出し用）。"""
    decision = AIDecision(
        user_id=request.user_id,
        query=request.query,
        action=request.action,
        confidence=request.confidence,
        reason=request.reason,
        primary_provider=request.primary_provider,
        primary_action=request.primary_action,
        primary_confidence=request.primary_confidence,
        secondary_provider=request.secondary_provider,
        secondary_action=request.secondary_action,
        secondary_confidence=request.secondary_confidence,
        agreed=request.agreed,
        rag_context_json=request.rag_context_json,
        prompt_version=request.prompt_version,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return AIDecisionResponse.model_validate(decision)
