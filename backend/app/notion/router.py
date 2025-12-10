# backend/app/notion/router.py

from fastapi import APIRouter, HTTPException, status

from app.notion.schemas import NotionIngestResponse
from app.notion.service import NotionService

router = APIRouter(prefix="/notion", tags=["notion"])

_service = NotionService()


@router.post(
    "/ingest",
    response_model=NotionIngestResponse,
    summary="Notion から未処理ニュースを取得",
    description="Status=未処理 かつ URL が設定されているニュースだけを Notion から取得する。",
)
def ingest_from_notion() -> NotionIngestResponse:
    """
    Notion から未処理ニュースを取得するエンドポイント。

    - 正常系: NotionService.fetch_unprocessed_news() の結果をそのまま返す
    - 異常系: 予期しない例外発生時には 500 エラーとして扱う
    """
    try:
        items = _service.fetch_unprocessed_news()
    except Exception as exc:  # noqa: BLE001
        # 予期しない例外は 500 としてクライアントに返す（詳細はログ側で確認）
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch news from Notion.",
        ) from exc

    return NotionIngestResponse(items=items, count=len(items))

