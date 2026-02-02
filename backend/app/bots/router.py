# backend/app/bots/router.py
from functools import lru_cache
import os

from fastapi import APIRouter, Depends, HTTPException, status

from .client import OctoBotClient
from .config import get_octobot_settings
from .schemas import OctoBotSignalRequest, OctoBotSignalResponse
from .service import OctoBotService

router = APIRouter(tags=["octobot"])


@lru_cache()
def get_octobot_service() -> OctoBotService:
    """
    OctoBotService のシングルトンインスタンスを取得する。
    """
    settings = get_octobot_settings()
    client = OctoBotClient(settings=settings)
    
    return OctoBotService(
        client=client,
        min_confidence=70,
        max_same_action_per_hour=3,
    )


@router.post(
    "/octobot/signal",
    response_model=OctoBotSignalResponse,
    summary="AI 判定結果をもとに OctoBot へシグナル送信",
)
def post_octobot_signal(
    body: OctoBotSignalRequest,
    service: OctoBotService = Depends(get_octobot_service),
) -> OctoBotSignalResponse:
    """
    AIAnalysisResult 相当のシグナル配列を受け取り、OctoBot 外部 API へ送信するエンドポイント。
    """
    try:
        body.validate_count()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        return service.process_signals(body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while processing OctoBot signals.",
        ) from exc
