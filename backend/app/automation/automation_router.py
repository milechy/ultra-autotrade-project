# backend/app/automation/automation_router.py
"""
自動化ワークフロー用 API エンドポイント。

POST /automation/process-news:
  Notion → AI → OctoBot → Notion書き戻し の全フローを実行
"""

import logging
from functools import lru_cache
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.service import AIService
from app.bots.router import get_octobot_service
from app.bots.service import OctoBotService
from app.notion.service import NotionService

from .workflow import WorkflowResult, WorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["automation"])


class ProcessNewsResponse(BaseModel):
    """POST /automation/process-news のレスポンス。"""

    fetched_count: int = Field(..., description="Notionから取得した未処理ニュース件数")
    analyzed_count: int = Field(..., description="AI判定した件数")
    octobot_success_count: int = Field(..., description="OctoBot送信成功件数")
    octobot_skipped_count: int = Field(..., description="OctoBotスキップ件数")
    octobot_failed_count: int = Field(..., description="OctoBot送信失敗件数")
    notion_updated_count: int = Field(..., description="Notion書き戻し成功件数")
    errors: List[str] = Field(default_factory=list, description="エラーメッセージ一覧")
    status: str = Field(
        ...,
        description="処理ステータス (completed / completed_with_errors / failed)",
    )


@lru_cache()
def get_notion_service() -> NotionService:
    """NotionService のシングルトンインスタンスを取得する。"""
    return NotionService()


@lru_cache()
def get_ai_service() -> AIService:
    """AIService のシングルトンインスタンスを取得する。"""
    return AIService()


def get_workflow_service(
    notion_service: NotionService = Depends(get_notion_service),
    ai_service: AIService = Depends(get_ai_service),
    octobot_service: OctoBotService = Depends(get_octobot_service),
) -> WorkflowService:
    """WorkflowService のインスタンスを取得する。"""
    return WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )


@router.post(
    "/automation/process-news",
    response_model=ProcessNewsResponse,
    summary="Notion → AI → OctoBot → Notion書き戻し の自動フローを実行",
)
def process_news(
    service: WorkflowService = Depends(get_workflow_service),
) -> ProcessNewsResponse:
    """
    未処理ニュースを取得し、AI判定→OctoBot送信→Notion書き戻しを行う。

    このエンドポイントは cron や手動トリガーで呼び出されることを想定。
    """
    logger.info("POST /automation/process-news called")

    try:
        result: WorkflowResult = service.process_pending_news()
    except Exception as exc:
        # 詳細はログに記録（デバッグ用）、レスポンスには一般的なメッセージのみ
        logger.error("Workflow execution failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during news processing",
        ) from exc

    # ステータスの決定
    # - completed: 全て成功
    # - completed_with_errors: 一部失敗（OctoBot送信失敗、Notion書き戻し失敗など）
    # - failed: 全て失敗
    has_errors = bool(result.errors) or result.octobot_failed_count > 0

    if has_errors:
        if result.notion_updated_count > 0 or result.octobot_success_count > 0:
            status_str = "completed_with_errors"
        else:
            status_str = "failed"
    else:
        status_str = "completed"

    logger.info(
        "POST /automation/process-news completed: status=%s, fetched=%d, analyzed=%d",
        status_str,
        result.fetched_count,
        result.analyzed_count,
    )

    return ProcessNewsResponse(
        fetched_count=result.fetched_count,
        analyzed_count=result.analyzed_count,
        octobot_success_count=result.octobot_success_count,
        octobot_skipped_count=result.octobot_skipped_count,
        octobot_failed_count=result.octobot_failed_count,
        notion_updated_count=result.notion_updated_count,
        errors=result.errors,
        status=status_str,
    )
