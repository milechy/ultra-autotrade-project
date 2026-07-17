# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_error_handler_structured_detail.py
"""production 環境の 4xx エラーで dict の detail(自前コードが構築した安全な構造化
エラー)がマスクされず、frontend の detail.code 分岐(DEPOSIT_BELOW_MINIMUM 等)が
機能することを検証する。detail=str(exc) 由来の生文字列は引き続きマスクされる
（内部情報漏洩防止、本ハンドラの本来の目的）ことも確認する。

2026-07-17 本番実機で発見: おまかせ切替の入金ゲート(DEPOSIT_BELOW_MINIMUM)が
"Validation error" に潰され、正しいトースト文言が出せなかった不具合の回帰テスト。
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import app.error_handlers as error_handlers_module
from app.error_handlers import register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/dict-detail")
    async def dict_detail_route() -> None:
        raise HTTPException(
            status_code=422,
            detail={"code": "DEPOSIT_BELOW_MINIMUM", "message": "最低$200の入金が必要です"},
        )

    @app.get("/string-detail")
    async def string_detail_route() -> None:
        raise HTTPException(status_code=400, detail="ValueError: internal db path leaked")

    return app


def test_production_preserves_dict_detail(monkeypatch) -> None:
    """production でも dict detail はマスクされず、code フィールドが読める。"""
    monkeypatch.setattr(error_handlers_module, "_is_production", True)
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/dict-detail")

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "DEPOSIT_BELOW_MINIMUM"
    assert body["detail"]["message"] == "最低$200の入金が必要です"


def test_production_masks_string_detail(monkeypatch) -> None:
    """production では文字列 detail は引き続き安全なメッセージにマスクされる。"""
    monkeypatch.setattr(error_handlers_module, "_is_production", True)
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/string-detail")

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Bad request"
    assert "internal db path" not in body["detail"]


def test_non_production_passes_through_unmasked(monkeypatch) -> None:
    """production 以外(development/staging)では従来通りマスクしない。"""
    monkeypatch.setattr(error_handlers_module, "_is_production", False)
    client = TestClient(_make_app(), raise_server_exceptions=False)

    dict_response = client.get("/dict-detail")
    assert dict_response.json()["detail"]["code"] == "DEPOSIT_BELOW_MINIMUM"

    string_response = client.get("/string-detail")
    assert "internal db path leaked" in string_response.json()["detail"]
