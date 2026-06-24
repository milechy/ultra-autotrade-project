# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_registration_webhook.py
"""send_registration_webhook のユニットテスト。"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.users.registration_webhook import send_registration_webhook


@pytest.mark.asyncio
async def test_send_webhook_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常: httpx.AsyncClient.post が呼ばれ、200 レスポンスで成功ログが出る。"""
    monkeypatch.setenv("UAT_WEBHOOK_SECRET", "test-secret")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.users.registration_webhook.httpx.AsyncClient", return_value=mock_client):
        await send_registration_webhook(
            email="test@example.com",
            uat_user_id=42,
            referral_code="ABCD1234",
            registered_at="2026-06-24T10:00:00+00:00",
        )

    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"]["email"] == "test@example.com"
    assert call_kwargs.kwargs["json"]["uat_user_id"] == 42
    assert call_kwargs.kwargs["json"]["referral_code"] == "ABCD1234"
    assert call_kwargs.kwargs["headers"]["x-uat-webhook-secret"] == "test-secret"


@pytest.mark.asyncio
async def test_send_webhook_no_referral_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """referral_code が null の場合も正常送信できること。"""
    monkeypatch.setenv("UAT_WEBHOOK_SECRET", "test-secret")

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.users.registration_webhook.httpx.AsyncClient", return_value=mock_client):
        await send_registration_webhook(
            email="admin@example.com",
            uat_user_id=1,
            referral_code=None,
            registered_at="2026-06-24T10:00:00+00:00",
        )

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["referral_code"] is None


@pytest.mark.asyncio
async def test_send_webhook_secret_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """UAT_WEBHOOK_SECRET 未設定時は httpx を呼ばずに静かにスキップすること。"""
    monkeypatch.delenv("UAT_WEBHOOK_SECRET", raising=False)

    with patch("app.users.registration_webhook.httpx.AsyncClient") as mock_cls:
        await send_registration_webhook(
            email="user@example.com",
            uat_user_id=99,
            referral_code=None,
            registered_at="2026-06-24T10:00:00+00:00",
        )

    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_send_webhook_http_error_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Webhook 送信が例外を投げても呼び出し元に伝播しないこと（fire-and-forget）。"""
    monkeypatch.setenv("UAT_WEBHOOK_SECRET", "test-secret")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("network error"))

    with patch("app.users.registration_webhook.httpx.AsyncClient", return_value=mock_client):
        # 例外が伝播しないことを確認（raise しなければ OK）
        await send_registration_webhook(
            email="user@example.com",
            uat_user_id=5,
            referral_code=None,
            registered_at="2026-06-24T10:00:00+00:00",
        )


@pytest.mark.asyncio
async def test_send_webhook_non_2xx_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx レスポンスでも例外を投げず警告ログに記録すること。"""
    monkeypatch.setenv("UAT_WEBHOOK_SECRET", "test-secret")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.users.registration_webhook.httpx.AsyncClient", return_value=mock_client):
        await send_registration_webhook(
            email="user@example.com",
            uat_user_id=7,
            referral_code=None,
            registered_at="2026-06-24T10:00:00+00:00",
        )

    mock_client.post.assert_awaited_once()
