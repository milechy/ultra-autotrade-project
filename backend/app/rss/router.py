# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/rss/router.py

"""
RSS API エンドポイント。

POST /rss/fetch  - RSS フィードを取得して Knowledge Hub に登録する
GET  /rss/feeds  - 設定済みフィード一覧を返す
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.knowledge.router import get_knowledge_service
from app.knowledge.service import KnowledgeService
from app.rss.fetcher import DEFAULT_FEEDS, RSSFetcher
from app.rss.schemas import RSSFeedConfig, RSSFetchResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rss", tags=["rss"])


@router.post(
    "/fetch",
    response_model=RSSFetchResult,
    summary="RSS フィード取得・登録",
)
def fetch_rss(
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> RSSFetchResult:
    """
    設定済み RSS フィードを全て取得し、新規エントリを Knowledge Hub に登録する。

    - 重複 URL はスキップする
    - エラー発生時も処理を継続する（fail-safe）
    """
    fetcher = RSSFetcher(knowledge_service=service)
    results = fetcher.fetch_and_register(db)
    total = sum(results.values())

    logger.info(
        "RSS fetch API called",
        extra={"results": results, "total": total},
    )

    return RSSFetchResult(results=results, total=total)


@router.get(
    "/feeds",
    response_model=list[RSSFeedConfig],
    summary="RSS フィード設定一覧",
)
def list_feeds() -> list[RSSFeedConfig]:
    """
    設定済み RSS フィードの一覧を返す。
    """
    return DEFAULT_FEEDS
