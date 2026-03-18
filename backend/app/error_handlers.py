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


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if _is_production and exc.status_code >= 500:
            logger.error(
                "HTTP %s: %s", exc.status_code, exc.detail, extra={"path": str(request.url.path)}
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": SAFE_MESSAGES.get(exc.status_code, "Internal server error")},
            )
        if _is_production and exc.status_code >= 400:
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
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {exc}"},
        )
