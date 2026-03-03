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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
