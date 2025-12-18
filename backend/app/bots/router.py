# backend/app/bots/router.py
from __future__ import annotations

import inspect
import os
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from .client import OctoBotClient
from .schemas import OctoBotSignalRequest, OctoBotSignalResponse
from .service import OctoBotService

router = APIRouter(tags=["octobot"])


def _build_octobot_client(*, api_base_url: str, api_key: str) -> OctoBotClient:
    """
    OctoBotClient の __init__ シグネチャ差異に追従して生成する。

    例:
      - OctoBotClient(base_url=..., api_key=...)
      - OctoBotClient(api_base_url=..., api_key=...)
      - OctoBotClient(api_url=..., api_key=...)
      - OctoBotClient(url=..., api_key=...)
      - OctoBotClient(api_base_url, api_key) など（位置引数）
    """
    sig = inspect.signature(OctoBotClient.__init__)
    params = sig.parameters

    # self を除いた引数名集合
    names = [pname for pname in params.keys() if pname != "self"]

    # まずはキーワードで渡せるかを試す（よくある命名を順に）
    url_key_candidates = ["base_url", "api_base_url", "api_url", "url", "endpoint"]
    key_key_candidates = ["api_key", "token", "key"]

    kw: dict[str, str] = {}

    url_key = next((k for k in url_key_candidates if k in names), None)
    if url_key:
        kw[url_key] = api_base_url

    key_key = next((k for k in key_key_candidates if k in names), None)
    if key_key:
        kw[key_key] = api_key

    # kwargs で必要十分に渡せる場合
    if kw:
        try:
            return OctoBotClient(**kw)  # type: ignore[arg-type]
        except TypeError:
            # シグネチャがより厳密/位置引数のみ等の可能性があるので fallback へ
            pass

    # fallback: 位置引数で渡す
    try:
        return OctoBotClient(api_base_url, api_key)  # type: ignore[arg-type]
    except TypeError:
        # さらに fallback: url だけ/ key だけ等の特殊形
        try:
            return OctoBotClient(api_base_url)  # type: ignore[arg-type]
        except TypeError as e:
            raise RuntimeError(
                "Failed to construct OctoBotClient: unsupported __init__ signature"
            ) from e


@lru_cache()
def get_octobot_service() -> OctoBotService:
    """
    OctoBotService のシングルトンインスタンスを取得する。

    NOTE:
      - テストでは monkeypatch で環境変数がセットされる前提。
      - 本番では infra / config 層で環境変数が設定される前提。
    """
    base_url = os.getenv("OCTOBOT_API_BASE_URL")
    api_key = os.getenv("OCTOBOT_API_KEY")

    if not base_url:
        raise RuntimeError("OCTOBOT_API_BASE_URL is not set")
    if not api_key:
        raise RuntimeError("OCTOBOT_API_KEY is not set")

    client = _build_octobot_client(api_base_url=base_url, api_key=api_key)

    return OctoBotService(
        client=client,
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
        body.validate_count()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        return service.process_signals(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while processing OctoBot signals.",
        ) from exc
