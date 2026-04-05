# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_cors_500_handler.py
"""Tests for CORS headers on 500 error responses.

教訓: FastAPI は未処理例外で CORSMiddleware を通さないため、
ブラウザでは CORS エラーに見えて実際の原因の特定が遅れる。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.error_handlers import register_error_handlers

ALLOWED_ORIGIN = "https://app.ultra-auto-trade.com"


def _make_app_with_crash_route() -> FastAPI:
    """Return a minimal test app with a route that raises an unhandled exception."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ALLOWED_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.cors_origins = [ALLOWED_ORIGIN]

    register_error_handlers(app)

    @app.get("/crash")
    async def crash_route() -> None:
        raise RuntimeError("simulated 500 error")

    return app


def test_500_includes_cors_header_for_allowed_origin() -> None:
    """500 エラー時にも CORS ヘッダーが返ることを確認。"""
    client = TestClient(_make_app_with_crash_route(), raise_server_exceptions=False)
    response = client.get("/crash", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_500_cors_credentials_header() -> None:
    """500 エラー時に credentials ヘッダーも付くことを確認。"""
    client = TestClient(_make_app_with_crash_route(), raise_server_exceptions=False)
    response = client.get("/crash", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_500_no_cors_for_unknown_origin() -> None:
    """許可されていない Origin には CORS ヘッダーを付けない。"""
    client = TestClient(_make_app_with_crash_route(), raise_server_exceptions=False)
    response = client.get("/crash", headers={"Origin": "https://evil.com"})
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


def test_500_no_cors_without_origin_header() -> None:
    """Origin ヘッダーなしのリクエスト（サーバー間通信等）には CORS ヘッダー不要。"""
    client = TestClient(_make_app_with_crash_route(), raise_server_exceptions=False)
    response = client.get("/crash")
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers
