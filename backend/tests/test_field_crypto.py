# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_field_crypto.py
"""field_crypto（PII フィールドレベル暗号化 / Track 2 層2）の単体テスト。

AES-256-GCM 暗号化/復号のラウンドトリップ、バージョン埋め込み、KEK 未設定時の平文
パススルー(後方互換)、レガシー平文の透過復号、blind index の決定性・正規化を検証する。
"""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest

from app.security.field_crypto import (
    FieldCryptoError,
    blind_index,
    decrypt_pii,
    encrypt_pii,
    is_encryption_configured,
)

_KEK_V1 = base64.b64encode(b"\x01" * 32).decode()
_KEK_V2 = base64.b64encode(b"\x02" * 32).decode()
_BIDX_KEY = base64.b64encode(b"\x09" * 32).decode()


def _env(**kw: str) -> dict[str, str]:
    """PII 系 env をクリアしてから指定値をセットする patch.dict 用 dict を返す。"""
    base = {
        "PII_ENCRYPTION_KEK": "",
        "PII_KEK_VERSION": "",
        "PII_ENCRYPTION_KEK_V1": "",
        "PII_ENCRYPTION_KEK_V2": "",
        "PII_BLIND_INDEX_KEY": "",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# encrypt/decrypt round-trip
# ---------------------------------------------------------------------------


def test_roundtrip_with_kek():
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1, PII_KEK_VERSION="1")):
        ct = encrypt_pii("user@example.com")
        assert ct is not None
        assert ct.startswith("enc:v1:")
        assert "user@example.com" not in ct  # 平文が暗号文に露出しない
        assert decrypt_pii(ct) == "user@example.com"


def test_encrypt_none_returns_none():
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1)):
        assert encrypt_pii(None) is None
        assert decrypt_pii(None) is None


def test_encrypt_is_idempotent_on_ciphertext():
    """既に enc: 済みの値は二重暗号化しない。"""
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1)):
        ct = encrypt_pii("a@b.com")
        assert encrypt_pii(ct) == ct


def test_encrypt_uses_random_nonce():
    """同一平文でも nonce により暗号文は毎回変わる(決定的でない)。"""
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1)):
        assert encrypt_pii("same@x.com") != encrypt_pii("same@x.com")


# ---------------------------------------------------------------------------
# KEK 未設定 = 平文パススルー(後方互換)
# ---------------------------------------------------------------------------


def test_no_kek_passthrough():
    with patch.dict(os.environ, _env()):
        assert is_encryption_configured() is False
        assert encrypt_pii("plain@x.com") == "plain@x.com"
        assert decrypt_pii("plain@x.com") == "plain@x.com"


def test_legacy_plaintext_read_with_kek():
    """KEK 設定後も enc: prefix 無しの既存平文はそのまま読める(段階移行)。"""
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1)):
        assert decrypt_pii("legacy-plain@x.com") == "legacy-plain@x.com"


# ---------------------------------------------------------------------------
# 鍵ローテ(版番号)
# ---------------------------------------------------------------------------


def test_decrypt_old_version_after_rotation():
    """v1 で暗号化 → v2 にローテ後も、旧版 KEK があれば v1 暗号文を復号できる。"""
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1, PII_KEK_VERSION="1")):
        ct_v1 = encrypt_pii("rotate@x.com")
    # ローテ: 現行を v2 に、旧 v1 鍵を PII_ENCRYPTION_KEK_V1 に保持
    with patch.dict(
        os.environ,
        _env(PII_ENCRYPTION_KEK=_KEK_V2, PII_KEK_VERSION="2", PII_ENCRYPTION_KEK_V1=_KEK_V1),
    ):
        assert decrypt_pii(ct_v1) == "rotate@x.com"
        # 新規暗号化は v2
        assert encrypt_pii("new@x.com").startswith("enc:v2:")


def test_decrypt_missing_version_key_raises():
    """版に対応する KEK が無ければ FieldCryptoError。"""
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1, PII_KEK_VERSION="1")):
        ct_v1 = encrypt_pii("x@x.com")
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V2, PII_KEK_VERSION="2")):
        with pytest.raises(FieldCryptoError):
            decrypt_pii(ct_v1)


def test_tampered_ciphertext_raises():
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK_V1)):
        ct = encrypt_pii("tamper@x.com")
        # base64 本体を 1 文字改ざん
        head, blob = ct.rsplit(":", 1)
        bad = f"{head}:{'A' if blob[0] != 'A' else 'B'}{blob[1:]}"
        with pytest.raises(FieldCryptoError):
            decrypt_pii(bad)


def test_invalid_kek_length_raises():
    short = base64.b64encode(b"\x01" * 16).decode()
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=short)):
        with pytest.raises(FieldCryptoError):
            encrypt_pii("x@x.com")


# ---------------------------------------------------------------------------
# blind_index
# ---------------------------------------------------------------------------


def test_blind_index_deterministic_and_normalized():
    with patch.dict(os.environ, _env(PII_BLIND_INDEX_KEY=_BIDX_KEY)):
        a = blind_index("  User@Example.COM ")
        b = blind_index("user@example.com")
        assert a == b  # 大文字小文字・前後空白を正規化して一致
        assert len(a) == 64  # SHA-256 hex


def test_blind_index_none_returns_none():
    with patch.dict(os.environ, _env(PII_BLIND_INDEX_KEY=_BIDX_KEY)):
        assert blind_index(None) is None


def test_blind_index_no_key_raises():
    with patch.dict(os.environ, _env()):
        with pytest.raises(FieldCryptoError):
            blind_index("x@x.com")
