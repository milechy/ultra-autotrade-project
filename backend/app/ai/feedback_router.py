# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/feedback_router.py
"""AI判定フィードバック API ルーター (Layer 4)。

全エンドポイントは admin ロール限定。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.auth.models import User
from app.database import get_db

from .feedback_models import AIFeedbackCreate, AIFeedbackResponse, AIFeedbackStats
from .feedback_service import FeedbackService

router = APIRouter(prefix="/api/ai/feedback", tags=["ai-feedback"])


@router.post(
    "/record",
    response_model=AIFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="AI判定フィードバック記録",
    description="指定した AI 判定 ID に対してフィードバックを記録する。admin のみ。",
)
def record_feedback(
    data: AIFeedbackCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AIFeedbackResponse:
    """フィードバックを記録する。"""
    svc = FeedbackService(db)

    # ai_decision_id の存在確認は FeedbackService 外で行う
    # （サービスは DB 操作に集中、ルーターで 404 を返す）
    from sqlalchemy import select  # noqa: PLC0415

    from .models import AIDecision  # noqa: PLC0415

    decision = db.scalars(select(AIDecision).where(AIDecision.id == data.ai_decision_id)).first()
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI decision {data.ai_decision_id} not found",
        )

    feedback = svc.record_feedback(data, recorded_by=current_user.email)
    return AIFeedbackResponse.model_validate(feedback)


@router.get(
    "/stats",
    response_model=AIFeedbackStats,
    summary="フィードバック統計取得",
    description="期間を指定してフィードバック統計を取得する。admin のみ。days=0 で全期間。",
)
def get_feedback_stats(
    days: int = Query(default=30, ge=0, description="集計対象日数 (0=全期間)"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AIFeedbackStats:
    """フィードバック統計を返す。"""
    svc = FeedbackService(db)
    return svc.get_stats(days=days)


@router.get(
    "/{decision_id}",
    response_model=list[AIFeedbackResponse],
    summary="AI判定別フィードバック一覧",
    description="指定した AI 判定 ID に対するフィードバック一覧を返す。admin のみ。",
)
def get_feedback_by_decision(
    decision_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AIFeedbackResponse]:
    """特定の AI 判定に対するフィードバック一覧を返す。"""
    svc = FeedbackService(db)
    feedbacks = svc.get_feedback_by_decision(decision_id)
    return [AIFeedbackResponse.model_validate(f) for f in feedbacks]
