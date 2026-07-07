# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/privy/rest_client.py
"""Privy REST クライアント（v4 Phase 2-D-B.2）。

サーバ側から Privy REST API を直接叩く httpx クライアント。`@privy-io/node` を使わず
Python 単一言語で委譲署名（wallet action）と policy 作成を行う（spike で経路A GO確定・
方針=Python httpx REST）。認証は morpho_client と同じ Basic auth(app_id:app_secret) +
`privy-app-id` ヘッダ。wallet action には `privy-authorization-signature`(P-256, 2-D-B.1)
を付与する。

エンドポイント（SDK 実装から抽出）::

    POST /v1/wallets/{wallet_id}/rpc   # wallet action（personal_sign / wallet_sendCalls 等）
    POST /v1/policies                  # policy 作成（app-level / Basic auth のみ）

wallet action の署名対象 URL は **完全 URL（末尾スラッシュなし）** = base_url + path。
SDK は既定で `privy-request-expiry`(now+15分, ms 絶対値) を付け署名にも含めるため、本実装も
同じ値をヘッダと署名の両方に乗せる（不一致だと TEE 検証で reject される）。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from app.privy.auth_signature import authorization_signature_header

logger = logging.getLogger(__name__)

_PRIVY_API_BASE = "https://api.privy.io/v1"
_DEFAULT_TIMEOUT_SECONDS = 20
_DEFAULT_REQUEST_EXPIRY_MS = 15 * 60 * 1000  # SDK 既定と同じ 15 分


class PrivyRestError(RuntimeError):
    """Privy REST 呼び出しが非 2xx を返した。"""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Privy REST error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class PrivyRestClient:
    """Privy REST API クライアント（委譲署名 + policy 作成）。"""

    def __init__(
        self,
        *,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        authorization_private_keys: Optional[list[str]] = None,
        base_url: str = _PRIVY_API_BASE,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        request_expiry_ms: int = _DEFAULT_REQUEST_EXPIRY_MS,
    ) -> None:
        self._app_id = app_id or os.getenv("PRIVY_APP_ID") or ""
        self._app_secret = app_secret or os.getenv("PRIVY_APP_SECRET") or ""
        # authorization 秘密鍵（PKCS8 DER base64・PEM ヘッダなし）。env からも読む。
        if authorization_private_keys is not None:
            self._authz_keys = authorization_private_keys
        else:
            raw = os.getenv("PRIVY_AUTHORIZATION_PRIVATE_KEY", "")
            self._authz_keys = [raw] if raw else []
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._request_expiry_ms = request_expiry_ms
        if not self._app_id or not self._app_secret:
            raise ValueError("PRIVY_APP_ID / PRIVY_APP_SECRET are required")

    # -- 内部 ------------------------------------------------------------- #
    def _auth(self) -> tuple[str, str]:
        return (self._app_id, self._app_secret)

    def _base_headers(self) -> dict[str, str]:
        return {"privy-app-id": self._app_id, "Content-Type": "application/json"}

    def _expiry_now(self) -> int:
        """現在時刻 + 既定 expiry の絶対 unix ms。"""
        return int(time.time() * 1000) + self._request_expiry_ms

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        signed: bool,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = self._base_headers()
        request_expiry: Optional[int] = None
        if signed:
            if not self._authz_keys:
                raise ValueError("authorization_private_keys required for signed wallet action")
            request_expiry = self._expiry_now()
            headers["privy-request-expiry"] = str(request_expiry)
            if idempotency_key:
                headers["privy-idempotency-key"] = idempotency_key
            headers["privy-authorization-signature"] = authorization_signature_header(
                method="POST",
                url=url,
                body=body,
                app_id=self._app_id,
                authorization_private_keys=self._authz_keys,
                idempotency_key=idempotency_key,
                request_expiry=request_expiry,
            )
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=body, headers=headers, auth=self._auth())
        if resp.status_code // 100 != 2:
            # 秘密鍵 / 署名はログに出さない（CLAUDE.md §Security 8）。
            raise PrivyRestError(resp.status_code, resp.text[:500])
        data: dict[str, Any] = resp.json()
        return data

    # -- public API ------------------------------------------------------- #
    def wallet_rpc(
        self, wallet_id: str, body: dict[str, Any], *, idempotency_key: Optional[str] = None
    ) -> dict[str, Any]:
        """POST /v1/wallets/{id}/rpc（委譲署名つき wallet action）。"""
        return self._post(
            f"/wallets/{wallet_id}/rpc", body, signed=True, idempotency_key=idempotency_key
        )

    def sign_message(self, wallet_id: str, message: str) -> dict[str, Any]:
        """personal_sign（UTF-8 文字列）。live 受理検証 / 動作確認用。"""
        body = {
            "method": "personal_sign",
            "params": {"message": message, "encoding": "utf-8"},
        }
        return self.wallet_rpc(wallet_id, body)

    def send_calls(
        self,
        wallet_id: str,
        *,
        caip2: str,
        calls: list[dict[str, Any]],
        sponsor: bool = True,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """ERC-5792 wallet_sendCalls（smart wallet 経由の sponsored 送信）。2-D-C で使用。"""
        body: dict[str, Any] = {
            "method": "wallet_sendCalls",
            "caip2": caip2,
            "sponsor": sponsor,
            "params": {"calls": calls},
        }
        return self.wallet_rpc(wallet_id, body, idempotency_key=idempotency_key)

    def send_transaction(
        self,
        wallet_id: str,
        *,
        caip2: str,
        transaction: dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """eth_sendTransaction（EOA server wallet が自身の tx を TEE 内署名して送信）。

        smart wallet の `send_calls`(ERC-5792) と異なり、operator 自身の EOA wallet が
        単一 tx を署名・broadcast する経路。手数料徴収 (aToken.transferFrom) の
        Privy 化に使う。生鍵 (`OPERATOR_FEE_WALLET_KEY`) 経路の置換。

        :param wallet_id: operator の **Privy 内部 wallet ID**（アドレスではない）
        :param caip2: 執行チェーン（``eip155:<chain_id>``・`scw_executor.caip2_for_chain`）
        :param transaction: ``{to, data, value}``（nonce/gas は Privy が補完）
        """
        body: dict[str, Any] = {
            "method": "eth_sendTransaction",
            "caip2": caip2,
            "params": {"transaction": transaction},
        }
        return self.wallet_rpc(wallet_id, body, idempotency_key=idempotency_key)

    def create_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/policies（app-level / Basic auth のみ・委譲署名不要）。"""
        return self._post("/policies", policy, signed=False)

    def create_wallet(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/wallets（server wallet 作成・app-level / Basic auth のみ）。

        operator fee wallet を Privy Server Wallet として作成する 1 回限りセットアップ用。
        body 例::

            {
                "chain_type": "ethereum",
                "policy_ids": ["<operator fee policy id>"],
                "authorization_key_ids": ["<server signer / key quorum id>"],
            }

        返り値の ``id`` が ``OPERATOR_FEE_PRIVY_WALLET_ID``、``address`` が
        ``OPERATOR_FEE_WALLET_ADDRESS`` になる。実 body 形状は Privy API reference に従い
        セットアップスクリプト側で組む（本メソッドは薄い POST ラッパ）。
        """
        return self._post("/wallets", body, signed=False)

    def create_key_quorum(
        self,
        *,
        public_keys: list[str],
        authorization_threshold: int = 1,
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """POST /v1/key_quorums（L0: サーバ authorization key を quorum 登録）。

        app-level 操作で **Basic auth のみ**（委譲署名不要）。SDK の
        `KeyQuorums.create` は `update`/`delete` と異なり authorization-signature を付けない
        （`node_modules/@privy-io/node/resources/key-quorums.js` の create で確認）。

        :param public_keys: P-256 公開鍵（SPKI DER の base64・PEM ヘッダなし）のリスト
        :param authorization_threshold: 必要署名数（既定 1 = 単独サーバ signer）
        :param display_name: 監査用表示名
        :return: 作成された key quorum（``id`` が SERVER_SIGNER_ID = signerId）
        """
        if not public_keys:
            raise ValueError("public_keys must not be empty")
        body: dict[str, Any] = {
            "public_keys": public_keys,
            "authorization_threshold": authorization_threshold,
        }
        if display_name:
            body["display_name"] = display_name
        return self._post("/key_quorums", body, signed=False)
