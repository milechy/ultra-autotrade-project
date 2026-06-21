# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_server_keys.py
"""server_keys（サーバ authorization 鍵の生成・公開鍵導出）の単体テスト（L0）。

生成鍵が Privy の要求形式（PKCS8 DER base64 秘密 / SPKI DER base64 公開）であり、
auth_signature の署名フローとラウンドトリップすることを検証する。
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

from app.privy.auth_signature import (
    canonical_payload,
    load_authorization_private_key,
    sign_payload,
)
from app.privy.server_keys import (
    derive_public_key_spki_b64,
    generate_server_authorization_keypair,
)


def test_generate_keypair_formats() -> None:
    priv_b64, pub_b64 = generate_server_authorization_keypair()
    # 秘密鍵は auth_signature がロードできる PKCS8 DER base64
    key = load_authorization_private_key(priv_b64)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert isinstance(key.curve, ec.SECP256R1)
    # 公開鍵は SPKI DER base64（load_der_public_key でロードできる）
    pub = load_der_public_key(base64.b64decode(pub_b64))
    assert isinstance(pub, ec.EllipticCurvePublicKey)


def test_generated_public_matches_private() -> None:
    priv_b64, pub_b64 = generate_server_authorization_keypair()
    derived = derive_public_key_spki_b64(priv_b64)
    assert derived == pub_b64


def test_keypairs_are_unique() -> None:
    p1, _ = generate_server_authorization_keypair()
    p2, _ = generate_server_authorization_keypair()
    assert p1 != p2


def test_sign_verify_roundtrip() -> None:
    """生成した秘密鍵で署名 → 導出した公開鍵で検証できる。"""
    priv_b64, pub_b64 = generate_server_authorization_keypair()
    key = load_authorization_private_key(priv_b64)
    payload = canonical_payload(
        {"version": 1, "method": "POST", "url": "https://x", "body": "", "headers": {}}
    )
    sig_b64 = sign_payload(payload, key)

    pub = load_der_public_key(base64.b64decode(pub_b64))
    assert isinstance(pub, ec.EllipticCurvePublicKey)
    # 例外が出なければ検証成功
    pub.verify(base64.b64decode(sig_b64), payload, ec.ECDSA(hashes.SHA256()))


def test_derive_from_known_key() -> None:
    """既存秘密鍵から公開鍵を導出（spike 鍵再利用シナリオ）。"""
    key = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    priv_b64 = base64.b64encode(
        key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    ).decode("ascii")
    derived = derive_public_key_spki_b64(priv_b64)
    assert base64.b64decode(derived)  # 有効な base64 SPKI
