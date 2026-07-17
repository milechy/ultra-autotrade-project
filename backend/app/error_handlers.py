# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Global error handlers for production safety.
Prevents internal error details from leaking to clients.
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_is_production = os.getenv("APP_ENV", "development") == "production"

SAFE_MESSAGES = {
    400: "Bad request",
    401: "Authentication required",
    403: "Access denied",
    404: "Resource not found",
    405: "Method not allowed",
    409: "Conflict",
    422: "Validation error",
    429: "Too many requests",
    500: "Internal server error",
    502: "Service unavailable",
    503: "Service unavailable",
}


def _add_cors_headers(response: JSONResponse, request: Request) -> None:
    """500 エラー時にも CORS ヘッダーを付与する。

    教訓: FastAPI は未処理例外で CORSMiddleware を通さないため、
    ブラウザでは CORS エラーに見えて実際の原因（DB カラム不足等）の特定が遅れる。
    """
    origin = request.headers.get("origin", "")
    if not origin:
        return
    allowed_origins: list[str] = getattr(request.app.state, "cors_origins", [])
    if origin in allowed_origins or "*" in allowed_origins:
        response.headers["access-control-allow-origin"] = origin
        response.headers["access-control-allow-credentials"] = "true"


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if _is_production and exc.status_code >= 500:
            logger.error(
                "HTTP %s: %s", exc.status_code, exc.detail, extra={"path": str(request.url.path)}
            )
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": SAFE_MESSAGES.get(exc.status_code, "Internal server error")},
            )
            _add_cors_headers(response, request)
            return response
        if _is_production and exc.status_code >= 400:
            # dict の detail は自前コードが意図的に構築した安全な構造化エラー
            # (例: {"code": "DEPOSIT_BELOW_MINIMUM", "message": ..., ...})。
            # マスクすると frontend の detail.code 分岐が壊れ、汎用エラーしか
            # 出せなくなる(2026-07-17 本番実機: おまかせ切替の入金ゲートで発見。
            # DEPOSIT_BELOW_MINIMUM が "Validation error" に潰され、正しい
            # トースト文言 [最低$200の入金が必要] が表示できなかった)。
            # detail=str(exc) 由来の生文字列のみ引き続きマスクする(内部情報漏洩防止、
            # 本ハンドラの本来の目的)。
            if isinstance(exc.detail, dict):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                )
            safe_detail = SAFE_MESSAGES.get(exc.status_code, str(exc.detail))
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": safe_detail},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception: %s", exc, exc_info=True, extra={"path": str(request.url.path)}
        )
        if _is_production:
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        else:
            response = JSONResponse(
                status_code=500,
                content={"detail": f"Internal server error: {exc}"},
            )
        _add_cors_headers(response, request)
        return response
