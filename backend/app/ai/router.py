# backend/app/ai/router.py
"""
AI 解析用の FastAPI ルーター定義。

- /ai/analyze
"""

from fastapi import APIRouter, HTTPException, status

from .schemas import AIAnalysisRequest, AIAnalysisResponse
from .service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])

# アプリケーション全体で共有する AIService インスタンス
_service = AIService()


@router.post(
    "/analyze",
    response_model=AIAnalysisResponse,
    summary="ニュースの AI 解析",
    description=(
        "/notion/ingest で取得した NotionNewsItem の配列を受け取り、"
        "各ニュースに対する BUY/SELL/HOLD 判定を返す。"
    ),
)
def analyze_news(request: AIAnalysisRequest) -> AIAnalysisResponse:
    """
    ニュース配列を受け取り、AI 判定結果を返すエンドポイント。

    - docs/05_ai_judgement_rules.md のルールに従い、HOLD 優先で安全側の判定を行う
    - 予期しない例外発生時は 500 エラーとして扱う
    """
    try:
        results = _service.analyze_items(request.items)
    except Exception as exc:  # noqa: BLE001
        # 予期しない例外は 500 番台として扱う（詳細はログ側に残す）
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI analysis failed unexpectedly.",
        ) from exc

    return AIAnalysisResponse(results=results, count=len(results))

