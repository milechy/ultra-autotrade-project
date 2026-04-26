# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/knowledge/router.py

"""
Knowledge Hub API エンドポイント。

POST /knowledge/items           - ナレッジアイテム登録
GET  /knowledge/items           - アイテム一覧取得（status フィルタ対応）
POST /knowledge/search          - ベクトル検索
PUT  /knowledge/items/{item_id}/status - ステータス更新
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_editor, require_viewer
from app.auth.models import User
from app.automation.schemas import WorkflowRunResult
from app.database import get_db

from .schemas import (
    KnowledgeCreateRequest,
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from .service import KnowledgeService, KnowledgeServiceError

logger = logging.getLogger(__name__)


class SearchTestItem(BaseModel):
    content: str
    source: Optional[str]
    similarity_score: float
    created_at: Optional[str]


class SearchTestResponse(BaseModel):
    results: List[SearchTestItem]
    count: int
    query: str


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_knowledge_service() -> KnowledgeService:
    """
    KnowledgeService のインスタンスを生成して返すファクトリ関数。

    FastAPI の Depends で使用する。
    設定は環境変数から都度読み込む（lru_cache は使用しない）。
    """
    return KnowledgeService()


@router.post(
    "/items",
    response_model=KnowledgeItem,
    status_code=status.HTTP_201_CREATED,
    summary="ナレッジアイテム登録",
)
def create_item(
    request: KnowledgeCreateRequest,
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: User = Depends(require_editor),
) -> KnowledgeItem:
    """
    URL またはテキストを取り込み、チャンク分割・埋め込み生成を行い DB に保存する。

    - item_type=url の場合は source_url が必須。
    - item_type=text の場合は raw_text が必須。
    """
    try:
        item = service.create_item(db, request)
        logger.info(
            "Knowledge item created via API",
            extra={"item_id": item.id, "item_type": item.item_type},
        )
        return item
    except KnowledgeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Unexpected error in create_item: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/items",
    response_model=List[KnowledgeItem],
    summary="アイテム一覧取得",
)
def get_items(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: User = Depends(require_viewer),
) -> List[KnowledgeItem]:
    """
    登録済みナレッジアイテムの一覧を取得する。

    クエリパラメータ `status` で絞り込み可能（pending / analyzed / skipped / error）。
    """
    try:
        return service.get_items(db, status=status)
    except Exception as exc:
        logger.error("Unexpected error in get_items: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="ベクトル検索",
)
def search(
    request: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: User = Depends(require_viewer),
) -> KnowledgeSearchResponse:
    """
    クエリを埋め込みベクトルに変換し、pgvector コサイン類似度で検索する。

    - top_k: 返却する最大件数（1〜20、デフォルト 5）
    """
    try:
        results = service.search(db, request)
        return KnowledgeSearchResponse(
            results=results,
            count=len(results),
            query=request.query,
        )
    except KnowledgeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Unexpected error in search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.put(
    "/items/{item_id}/status",
    response_model=KnowledgeItem,
    summary="アイテムステータス更新",
)
def update_status(
    item_id: int,
    new_status: KnowledgeItemStatus,
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: User = Depends(require_editor),
) -> KnowledgeItem:
    """
    指定した ID のアイテムのステータスを更新する。

    リクエストボディに `KnowledgeItemStatus` の値を指定する。
    """
    try:
        item = service.update_status(db, item_id, new_status)
        logger.info(
            "Knowledge item status updated via API",
            extra={"item_id": item_id, "new_status": new_status},
        )
        return item
    except KnowledgeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Unexpected error in update_status: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/search/test",
    response_model=SearchTestResponse,
    summary="管理者向けRAG検索テスト",
)
def search_test(
    query: str = Query(..., min_length=1, description="検索クエリ文字列"),
    top_k: int = Query(default=5, ge=1, le=20, description="返却する最大件数"),
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: User = Depends(require_editor),
) -> SearchTestResponse:
    """
    クエリパラメータで指定した検索クエリを pgvector コサイン類似度で検索する（管理者テスト用）。
    """
    try:
        search_request = KnowledgeSearchRequest(query=query, top_k=top_k)
        results = service.search(db, search_request)
        test_results = [
            SearchTestItem(
                content=r.content,
                source=r.source_url or r.title,
                similarity_score=r.similarity,
                created_at=None,
            )
            for r in results
        ]
        return SearchTestResponse(results=test_results, count=len(test_results), query=query)
    except KnowledgeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Unexpected error in search_test: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/workflow/trigger",
    response_model=WorkflowRunResult,
    summary="手動ワークフロー実行（adminのみ）",
)
def workflow_trigger(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WorkflowRunResult:
    """
    pending 状態のナレッジアイテムをすべて処理する（RAG → AI → Exchange）。
    adminロールのみ実行可能。
    """
    from app.ai.service import AIService
    from app.automation.workflow import process_pending_knowledge
    from app.exchange.router import get_exchange_service

    try:
        result = process_pending_knowledge(
            db,
            knowledge_service=KnowledgeService(),
            ai_service=AIService(),
            exchange_service=get_exchange_service(),
            monitoring_service=None,
            user_id=current_user.id,
        )
        logger.info(
            "Workflow triggered via API",
            extra={"status": result.status, "fetched": result.fetched_count},
        )
        return result
    except Exception as exc:
        logger.error("Unexpected error in workflow_trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
