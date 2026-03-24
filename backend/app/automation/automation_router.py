# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/automation_router.py
"""
自動化ワークフロー用 API エンドポイント。

POST /automation/process-news:
  Knowledge Hub → RAG → AI Judge → Exchange の全フローを実行
"""

import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.service import AIService
from app.auth.dependencies import require_admin
from app.automation.monitoring_service import MonitoringService
from app.automation.rate_limiter import RateLimiterService, get_rate_limiter
from app.automation.rate_limiter_schemas import RateLimitStatus
from app.automation.state import get_monitoring_service
from app.automation.workflow import process_pending_knowledge
from app.database import get_db
from app.exchange.router import get_exchange_service
from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["automation"])


class ProcessNewsResponse(BaseModel):
    """POST /automation/process-news のレスポンス。"""

    fetched_count: int = Field(..., description="Knowledge Hub から取得した pending アイテム数")
    analyzed_count: int = Field(..., description="AI 判定した件数")
    octobot_success_count: int = Field(..., description="取引成功件数")
    octobot_skipped_count: int = Field(..., description="取引スキップ件数（HOLD含む）")
    octobot_failed_count: int = Field(..., description="取引失敗件数")
    notion_updated_count: int = Field(default=0, description="（廃止）常に 0")
    errors: List[str] = Field(default_factory=list, description="エラーメッセージ一覧")
    status: str = Field(
        ...,
        description="処理ステータス (completed / completed_with_errors / failed / no_items)",
    )


@router.get(
    "/automation/rate-limits",
    response_model=RateLimitStatus,
    summary="APIレート制限の使用状況を取得",
)
def get_rate_limits(
    limiter: RateLimiterService = Depends(get_rate_limiter),
) -> RateLimitStatus:
    """各APIのレート制限使用状況（インメモリスライディングウィンドウ）を返す。"""
    return limiter.get_status()


@router.post(
    "/automation/process-news",
    response_model=ProcessNewsResponse,
    summary="Knowledge Hub → RAG → AI Judge → Exchange の自動フローを実行",
)
def process_news(
    dry_run: bool = Query(default=True, description="If true, simulate trades"),
    db: Session = Depends(get_db),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> ProcessNewsResponse:
    """
    Knowledge Hub の pending アイテムを取得し、
    RAG 検索 → AI Judge → Exchange 注文 を実行する。
    """
    logger.info("POST /automation/process-news called")

    try:
        run_result = process_pending_knowledge(
            db,
            knowledge_service=KnowledgeService(),
            ai_service=AIService(),
            exchange_service=get_exchange_service(),
            monitoring_service=monitoring_service,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.error("Workflow execution failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during news processing",
        ) from exc

    has_errors = bool(run_result.errors)
    if has_errors:
        status_str = "completed_with_errors" if run_result.fetched_count > 0 else "failed"
    elif run_result.status == "no_items":
        status_str = "no_items"
    else:
        status_str = "completed"

    logger.info(
        "POST /automation/process-news completed: status=%s, fetched=%d, analyzed=%d",
        status_str,
        run_result.fetched_count,
        run_result.analyzed_count,
    )

    return ProcessNewsResponse(
        fetched_count=run_result.fetched_count,
        analyzed_count=run_result.analyzed_count,
        octobot_success_count=run_result.traded_count,
        octobot_skipped_count=(run_result.skipped_count or 0) + (run_result.hold_count or 0),
        octobot_failed_count=len(run_result.errors),
        notion_updated_count=0,
        errors=[e.message for e in run_result.errors],
        status=status_str,
    )


class AIJudgmentTriggerResponse(BaseModel):
    """POST /api/ai/trigger のレスポンス。"""

    action: str = Field(..., description="AI判定アクション (BUY/SELL/HOLD)")
    confidence: int = Field(..., description="信頼度スコア (0-100)")
    proposals_created: int = Field(..., description="作成された提案件数")
    decision_id: int = Field(..., description="保存されたai_decision ID")


@router.post(
    "/api/ai/trigger",
    response_model=AIJudgmentTriggerResponse,
    summary="AI判定を手動で即時実行する（管理者専用）",
)
def trigger_ai_judgment(
    db: Session = Depends(get_db),
    current_user: Any = Depends(require_admin),
) -> AIJudgmentTriggerResponse:
    """
    AI判定ジョブを手動で1回実行する（テスト・デバッグ用）。
    BUY/SELL判定時はアクティブユーザー全員にproposalを作成する。
    """
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job  # noqa: PLC0415

    logger.info("Manual AI judgment trigger by admin (user_id=%s)", current_user.id)
    try:
        result = run_ai_judgment_job(db=db)
    except Exception as exc:
        logger.error("Manual AI judgment failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI judgment execution failed",
        ) from exc
    return AIJudgmentTriggerResponse(**result)


class EmergencyStopResponse(BaseModel):
    """POST /automation/emergency-stop のレスポンス。"""

    status: str = Field(..., description="always 'stopped'")
    message: str = Field(..., description="緊急停止の確認メッセージ")


@router.post(
    "/automation/emergency-stop",
    response_model=EmergencyStopResponse,
    summary="全自動取引を即時停止する（管理者専用）",
)
def emergency_stop(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    current_user: Any = Depends(require_admin),
) -> EmergencyStopResponse:
    """
    全ての自動取引を即時停止する。一度停止すると clear_emergency_stop() を明示的に
    呼ぶまで再開されない（OR 条件で維持される）。
    """
    monitoring_service.activate_emergency_stop(
        reason=f"Manual emergency stop by admin (user_id={current_user.id})",
    )
    return EmergencyStopResponse(
        status="stopped",
        message="緊急停止が実行されました。全ての自動取引が停止されています。",
    )
