# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_auth_signature.py
"""Privy authorization-signature(P-256) の Python 実装検証（v4 Phase 2-D-B）。

Node SDK `@privy-io/node` の canonicalize(RFC 8785 JCS) 出力を **正解オラクル**として
ハードコードし、Python の canonical_payload が byte 一致することを検証する。
オラクルは dev VPS の harness `canon_oracle.mjs`（npm canonicalize 使用）で生成した実値。

検証:
1. canonicalize byte 一致（policy作成 / 空body / 混在型 の3サンプル）
2. SHA-256 一致
3. PKCS8 DER base64 鍵のロード + sign→verify ラウンドトリップ
4. 空 object body → "" 特例
5. 署名不能 method の拒否
"""

from __future__ import annotations

import base64
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from app.privy.auth_signature import (
    authorization_signature_header,
    build_signing_input,
    canonical_payload,
    load_authorization_private_key,
    sign_payload,
)

# --- Node オラクル実値（canon_oracle.mjs 出力, npm canonicalize=RFC8785 JCS） ---
_ORACLE = {
    "policy_create": {
        "input": dict(
            method="POST",
            url="https://api.privy.io/v1/policies",
            app_id="cmnv54q5f03ex0cjley894xrp",
            body={
                "version": "1.0",
                "name": "uata-spike-aave",
                "chain_type": "ethereum",
                "rules": [
                    {
                        "name": "allow-aave",
                        "method": "eth_sendTransaction",
                        "action": "ALLOW",
                        "conditions": [
                            {
                                "field_source": "ethereum_transaction",
                                "field": "to",
                                "operator": "eq",
                                "value": "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27",
                            }
                        ],
                    }
                ],
            },
        ),
        "canon": (
            '{"body":{"chain_type":"ethereum","name":"uata-spike-aave","rules":'
            '[{"action":"ALLOW","conditions":[{"field":"to","field_source":'
            '"ethereum_transaction","operator":"eq","value":'
            '"0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"}],"method":'
            '"eth_sendTransaction","name":"allow-aave"}],"version":"1.0"},'
            '"headers":{"privy-app-id":"cmnv54q5f03ex0cjley894xrp"},'
            '"method":"POST","url":"https://api.privy.io/v1/policies","version":1}'
        ),
        "sha256": "c4afe27c652e93991bfb4cf6b660089f42c8e371dce57e99ffbbec553934bda3",
    },
    "empty_body": {
        "input": dict(
            method="POST",
            url="https://api.privy.io/v1/wallets/abc/rpc",
            app_id="cmnv54q5f03ex0cjley894xrp",
            body={},
        ),
        "canon": (
            '{"body":"","headers":{"privy-app-id":"cmnv54q5f03ex0cjley894xrp"},'
            '"method":"POST","url":"https://api.privy.io/v1/wallets/abc/rpc","version":1}'
        ),
        "sha256": "5ddc3d9424a3fd3bd4168303c9417d6fae0b4946ee6f4153e7f9817d884a5c73",
    },
    "mixed": {
        "input": dict(
            method="POST",
            url="https://api.privy.io/v1/x",
            app_id="app1",
            body={"note": "ascii-only", "n": 42, "arr": [3, 1, 2], "nested": {"z": 1, "a": 2}},
        ),
        "canon": (
            '{"body":{"arr":[3,1,2],"n":42,"nested":{"a":2,"z":1},"note":"ascii-only"},'
            '"headers":{"privy-app-id":"app1"},"method":"POST",'
            '"url":"https://api.privy.io/v1/x","version":1}'
        ),
        "sha256": "514a899b5a9375893fed49e70a514cf15b1e2ba6da372d024b1d7097836d2164",
    },
}


@pytest.mark.parametrize("label", list(_ORACLE.keys()))
def test_canonicalize_matches_node_oracle(label: str) -> None:
    """Python canonicalize が Node(JCS) と byte 一致 + SHA256 一致。"""
    case = _ORACLE[label]
    si = build_signing_input(**case["input"])
    payload = canonical_payload(si)
    assert payload == case["canon"].encode("utf-8"), f"{label}: canonicalize mismatch"
    assert sha256(payload).hexdigest() == case["sha256"], f"{label}: sha256 mismatch"


def test_empty_object_body_becomes_empty_string() -> None:
    si = build_signing_input(method="POST", url="https://x/y", body={}, app_id="a")
    assert si["body"] == ""


def test_non_signable_method_rejected() -> None:
    with pytest.raises(ValueError):
        build_signing_input(method="GET", url="https://x/y", body={}, app_id="a")


def _new_key_b64() -> tuple[str, ec.EllipticCurvePublicKey]:
    """P-256 鍵を生成し PKCS8 DER base64（authorization_private_keys 形式）と公開鍵を返す。"""
    key = ec.generate_private_key(ec.SECP256R1())
    der = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return base64.b64encode(der).decode("ascii"), key.public_key()


def test_load_key_and_sign_verify_roundtrip() -> None:
    """PKCS8 DER base64 をロードし、署名→公開鍵 verify が通る（DER/sha256）。"""
    b64, pub = _new_key_b64()
    loaded = load_authorization_private_key(b64)
    assert isinstance(loaded, ec.EllipticCurvePrivateKey)

    payload = canonical_payload(
        build_signing_input(method="POST", url="https://x/y", body={"a": 1}, app_id="app")
    )
    sig_b64 = sign_payload(payload, loaded)
    der_sig = base64.b64decode(sig_b64)
    # 公開鍵で検証（例外なし=OK）
    pub.verify(der_sig, payload, ec.ECDSA(hashes.SHA256()))


def test_authorization_signature_header_multi_key() -> None:
    """複数鍵はカンマ連結され、各署名が対応公開鍵で verify できる。"""
    b1, pub1 = _new_key_b64()
    b2, pub2 = _new_key_b64()
    header = authorization_signature_header(
        method="POST",
        url="https://api.privy.io/v1/policies",
        body={"name": "x"},
        app_id="app",
        authorization_private_keys=[b1, b2],
    )
    parts = header.split(",")
    assert len(parts) == 2
    payload = canonical_payload(
        build_signing_input(
            method="POST", url="https://api.privy.io/v1/policies", body={"name": "x"}, app_id="app"
        )
    )
    pub1.verify(base64.b64decode(parts[0]), payload, ec.ECDSA(hashes.SHA256()))
    pub2.verify(base64.b64decode(parts[1]), payload, ec.ECDSA(hashes.SHA256()))
