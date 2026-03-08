# backend/app/automation/automation_router.py
"""
自動化ワークフロー用 API エンドポイント。

POST /automation/process-news:
  Knowledge Hub → RAG → AI Judge → Exchange の全フローを実行
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.service import AIService
from app.automation.monitoring_service import MonitoringService
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
