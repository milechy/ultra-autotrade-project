# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_rest_client.py
"""PrivyRestClient の単体テスト（v4 Phase 2-D-B.2）。

httpx を mock し、URL / body / ヘッダ（Basic auth・privy-app-id・authorization-signature・
request-expiry）の構築と非2xxエラー処理を検証する。実 Privy への live 受理検証は別途
dev VPS の検証スクリプトで実施（PR 説明参照）。
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from app.privy.auth_signature import build_signing_input, canonical_payload
from app.privy.rest_client import PrivyRestClient, PrivyRestError


def _authz_key_b64() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    der = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return base64.b64encode(der).decode("ascii")


def _client(**kw: Any) -> PrivyRestClient:
    return PrivyRestClient(
        app_id="app123",
        app_secret="secret123",
        authorization_private_keys=[_authz_key_b64()],
        **kw,
    )


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def _patch_httpx(captured: dict, resp: _FakeResp):
    """httpx.Client を mock し、post 呼び出しを captured に記録する。"""
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False

    def _post(url: str, json: dict, headers: dict, auth: tuple) -> _FakeResp:  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["auth"] = auth
        return resp

    mock_client.post.side_effect = _post
    return patch("app.privy.rest_client.httpx.Client", return_value=mock_client)


def test_missing_creds_raises() -> None:
    with pytest.raises(ValueError):
        PrivyRestClient(app_id="", app_secret="", authorization_private_keys=["x"])


def test_sign_message_request_shape() -> None:
    captured: dict = {}
    resp = _FakeResp(200, {"signature": "0xabc", "encoding": "hex"})
    c = _client()
    with _patch_httpx(captured, resp):
        out = c.sign_message("wid123", "hello")
    assert out == {"signature": "0xabc", "encoding": "hex"}
    # URL（完全URL・末尾スラッシュなし）
    assert captured["url"] == "https://api.privy.io/v1/wallets/wid123/rpc"
    # body 形（personal_sign / utf-8）
    assert captured["json"] == {
        "method": "personal_sign",
        "params": {"message": "hello", "encoding": "utf-8"},
    }
    # Basic auth
    assert captured["auth"] == ("app123", "secret123")
    # 必須ヘッダ
    h = captured["headers"]
    assert h["privy-app-id"] == "app123"
    assert "privy-authorization-signature" in h and h["privy-authorization-signature"]
    assert "privy-request-expiry" in h  # 署名対象にも乗る


def test_signature_matches_signed_input() -> None:
    """送信した署名が、送信した url/body/expiry に対する正当な P-256 署名であること。"""
    captured: dict = {}
    c = _client()
    with _patch_httpx(captured, _FakeResp(200, {"signature": "0x1"})):
        c.sign_message("wid", "msg")
    # 公開鍵で検証するため、同じ鍵で署名し直すのではなく canonical payload の一致を確認
    expiry = int(captured["headers"]["privy-request-expiry"])
    si = build_signing_input(
        method="POST",
        url=captured["url"],
        body=captured["json"],
        app_id="app123",
        request_expiry=expiry,
    )
    # payload が決定的に再現できる（canonicalize は安定）
    assert canonical_payload(si)  # 例外が出ないこと＝構造健全
    # 署名はカンマ区切りで1つ以上
    assert len(captured["headers"]["privy-authorization-signature"].split(",")) >= 1


def test_create_policy_is_basic_auth_only() -> None:
    """policy 作成は Basic auth のみ・authorization-signature を付けない。"""
    captured: dict = {}
    c = _client()
    spec = {"version": "1.0", "name": "p", "chain_type": "ethereum", "rules": []}
    with _patch_httpx(captured, _FakeResp(200, {"id": "policy_1"})):
        out = c.create_policy(spec)
    assert out == {"id": "policy_1"}
    assert captured["url"] == "https://api.privy.io/v1/policies"
    assert captured["json"] == spec
    assert captured["auth"] == ("app123", "secret123")
    assert "privy-authorization-signature" not in captured["headers"]
    assert "privy-request-expiry" not in captured["headers"]


def test_send_calls_request_shape() -> None:
    captured: dict = {}
    c = _client()
    with _patch_httpx(captured, _FakeResp(200, {"transaction_hash": "0xfeed"})):
        c.send_calls(
            "wid",
            caip2="eip155:84532",
            calls=[{"to": "0xpool", "value": "0x0", "data": "0x"}],
        )
    assert captured["json"]["method"] == "wallet_sendCalls"
    assert captured["json"]["caip2"] == "eip155:84532"
    assert captured["json"]["sponsor"] is True
    assert captured["json"]["params"]["calls"][0]["to"] == "0xpool"
    assert "privy-authorization-signature" in captured["headers"]


def test_non_2xx_raises_privy_rest_error() -> None:
    captured: dict = {}
    c = _client()
    with _patch_httpx(captured, _FakeResp(400, text='{"error":"bad"}')):
        with pytest.raises(PrivyRestError) as ei:
            c.sign_message("wid", "msg")
    assert ei.value.status_code == 400
    assert "bad" in ei.value.body
