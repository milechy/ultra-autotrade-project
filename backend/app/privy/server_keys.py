# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/privy/server_keys.py
"""サーバ authorization 鍵（P-256）の生成・公開鍵導出（v4 Phase 2-D-B.2 / L0）。

Privy の key quorum 登録（L0）に使うサーバ署名鍵を、Privy が要求する形式で扱う純関数群::

    秘密鍵 = PKCS8(DER, PEM ヘッダなし) の base64
             → env PRIVY_AUTHORIZATION_PRIVATE_KEY / SDK の authorization_private_keys と同形式
    公開鍵 = SPKI(DER) の base64
             → key quorum 作成の public_keys と同形式

spike で実証済の `openssl ecparam -name prime256v1` と同じ曲線（SECP256R1 = P-256）。
秘密鍵は **絶対にログに出さない**（CLAUDE.md §Security 1/8）。本 module は生成・導出のみで、
出力先（env / 標準出力）は呼び出し側が責任を持つ。
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from app.privy.auth_signature import load_authorization_private_key


def _private_pkcs8_b64(key: ec.EllipticCurvePrivateKey) -> str:
    der = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return base64.b64encode(der).decode("ascii")


def _public_spki_b64(key: ec.EllipticCurvePublicKey) -> str:
    der = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def generate_server_authorization_keypair() -> tuple[str, str]:
    """新しい P-256 サーバ authorization 鍵を生成する。

    :return: ``(private_key_b64_pkcs8_der, public_key_b64_spki_der)``
        - private: env ``PRIVY_AUTHORIZATION_PRIVATE_KEY`` に格納（秘匿・非コミット）
        - public:  key quorum 作成の ``public_keys`` に渡す
    """
    key = ec.generate_private_key(ec.SECP256R1())
    return _private_pkcs8_b64(key), _public_spki_b64(key.public_key())


def derive_public_key_spki_b64(private_key_b64_pkcs8: str) -> str:
    """既存の base64 PKCS8 秘密鍵から SPKI(DER) base64 公開鍵を導出する。

    spike で既に生成済の鍵（``~/.config/uata-privy-spike/.env`` 等）から、key quorum
    登録に渡す公開鍵を再現するのに使う。秘密鍵は戻り値に含めない。
    """
    key = load_authorization_private_key(private_key_b64_pkcs8)
    return _public_spki_b64(key.public_key())
