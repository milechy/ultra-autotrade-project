from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from .schemas import OctoBotSignalRequest, OctoBotSignalResponse
from .service import OctoBotService

router = APIRouter(tags=["octobot"])


@lru_cache()
def get_octobot_service() -> OctoBotService:
    """
    OctoBotService のシングルトンインスタンスを取得する。

    NOTE:
      - min_confidence 等の設定値は将来的に config/環境変数から取得する想定。
    """
    return OctoBotService(
        # TODO: min_confidence を docs/08_automation_rules.md から拾う
        min_confidence=0,
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

    - リクエスト整合性エラー → 400 Bad Request
    - 想定外の内部エラー → 500 Internal Server Error
    """
    try:
        # count と signals の長さの整合性チェック
        body.validate_count()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        return service.process_signals(body)
    except Exception as exc:  # noqa: BLE001
        # 想定外のエラーは 500 として返す。
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while processing OctoBot signals.",
        ) from exc
