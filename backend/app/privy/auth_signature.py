# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/privy/auth_signature.py
"""Privy authorization-signature (P-256) の生成（v4 Phase 2-D-B）。

`@privy-io/node` の `formatRequestForAuthorizationSignature` + `generateAuthorizationSignature`
を Python で再実装したもの。サーバが委譲署名（wallet action: signMessage / sendCalls 等）を
Privy REST API に投げる際に必要な `privy-authorization-signature` ヘッダ値を計算する。

仕様（Node SDK lib/authorization.js と一致）::

    input = {
        "version": 1,
        "method": <"POST"|"PUT"|"PATCH"|"DELETE">,
        "url": <リクエスト URL・末尾スラッシュなし>,
        "body": <リクエストボディ object・空 object は "" に置換>,
        "headers": {"privy-app-id": <app id>, ...(idempotency/expiry)},
    }
    payload = canonicalize(input)            # RFC 8785 JCS
    signature = base64(DER(P256_ECDSA(sha256(payload))))
    header "privy-authorization-signature" = ",".join(signatures)

canonicalize は Node SDK が npm `canonicalize`(RFC 8785 JCS) を使う。JCS は
キー再帰ソート / 配列順保持 / 余計な空白なし。ASCII ペイロード（アドレス・enum 文字列・
整数のみ。float なし）では `json.dumps(sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` が JCS と完全一致する（Node オラクルで byte 一致検証済み:
tests/test_privy_auth_signature.py）。**非 ASCII 文字や float を body に含めないこと**。

ECDSA P-256 は非決定的（k 乱択）のため署名 byte は毎回変わるが、Privy は公開鍵で検証する
ため任意の正当な署名で受理される。検証は (1) canonicalize payload の byte 一致 (2) 公開鍵での
verify ラウンドトリップ で行う。
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_private_key

_SIGNABLE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _jcs(obj: Any) -> str:
    """RFC 8785 JCS 互換の正規化文字列を返す（ASCII ペイロード前提）。

    Node SDK の `canonicalize` と一致することを Node オラクルで検証している。
    float / 非 ASCII を含む object は JCS と乖離しうるため使用しない。
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_signing_input(
    *,
    method: str,
    url: str,
    body: Any,
    app_id: str,
    idempotency_key: Optional[str] = None,
    request_expiry: Optional[int] = None,
) -> dict[str, Any]:
    """署名対象 input object を Node SDK の prepareRequest と同一構造で組み立てる。"""
    if method.upper() not in _SIGNABLE_METHODS:
        raise ValueError(
            f"method {method!r} is not signable (need one of {sorted(_SIGNABLE_METHODS)})"
        )
    serialized_body: Any = body
    # 空 object は "" にする（Node SDK 特例）。
    if isinstance(serialized_body, dict) and len(serialized_body) == 0:
        serialized_body = ""
    headers: dict[str, str] = {"privy-app-id": app_id}
    if idempotency_key:
        headers["privy-idempotency-key"] = idempotency_key
    if request_expiry is not None:
        headers["privy-request-expiry"] = str(request_expiry)
    return {
        "version": 1,
        "method": method.upper(),
        "url": url,
        "body": serialized_body,
        "headers": headers,
    }


def canonical_payload(signing_input: dict[str, Any]) -> bytes:
    """署名 input を canonicalize して UTF-8 bytes（=署名対象 payload）にする。"""
    return _jcs(signing_input).encode("utf-8")


def load_authorization_private_key(b64_pkcs8: str) -> ec.EllipticCurvePrivateKey:
    """base64-encoded PKCS8(DER, PEM ヘッダなし) の P-256 秘密鍵をロードする。

    形式は Node SDK の `authorization_private_keys` と同一
    （`openssl pkcs8 -topk8 -nocrypt -outform DER | base64`）。
    """
    der = base64.b64decode(b64_pkcs8)
    key = load_der_private_key(der, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("authorization key is not an EC (P-256) private key")
    return key


def sign_payload(payload: bytes, private_key: ec.EllipticCurvePrivateKey) -> str:
    """payload を sha256 + P-256 ECDSA で署名し DER→base64 文字列を返す。"""
    der_sig = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(der_sig).decode("ascii")


def authorization_signature_header(
    *,
    method: str,
    url: str,
    body: Any,
    app_id: str,
    authorization_private_keys: list[str],
    idempotency_key: Optional[str] = None,
    request_expiry: Optional[int] = None,
) -> str:
    """`privy-authorization-signature` ヘッダ値を計算する（複数鍵はカンマ連結）。"""
    signing_input = build_signing_input(
        method=method,
        url=url,
        body=body,
        app_id=app_id,
        idempotency_key=idempotency_key,
        request_expiry=request_expiry,
    )
    payload = canonical_payload(signing_input)
    signatures: list[str] = []
    for sk in authorization_private_keys:
        key = load_authorization_private_key(sk)
        signatures.append(sign_payload(payload, key))
    return ",".join(signatures)
