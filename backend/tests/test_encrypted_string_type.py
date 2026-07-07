# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_encrypted_string_type.py
"""EncryptedString TypeDecorator（Track 2 層2）の単体テスト。

ORM bind（write）で暗号化、result（read）で復号が透過的に走ることを、TypeDecorator の
process_bind_param / process_result_value を直接呼んで検証する（DB 不要）。
"""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

from app.security.sqlalchemy_types import EncryptedString

_KEK = base64.b64encode(b"\x03" * 32).decode()


def _env(**kw: str) -> dict[str, str]:
    base = {"PII_ENCRYPTION_KEK": "", "PII_KEK_VERSION": ""}
    base.update(kw)
    return base


def test_bind_encrypts_result_decrypts_roundtrip():
    t = EncryptedString(512)
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK, PII_KEK_VERSION="1")):
        stored = t.process_bind_param("secret@example.com", None)
        assert stored is not None
        assert stored.startswith("enc:v1:")
        assert "secret@example.com" not in stored
        assert t.process_result_value(stored, None) == "secret@example.com"


def test_bind_none_stays_none():
    t = EncryptedString(512)
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK)):
        assert t.process_bind_param(None, None) is None
        assert t.process_result_value(None, None) is None


def test_legacy_plaintext_read_passthrough():
    """DB に既にある平文（enc: 無し）は復号側でそのまま返る（段階移行）。"""
    t = EncryptedString(512)
    with patch.dict(os.environ, _env(PII_ENCRYPTION_KEK=_KEK)):
        assert t.process_result_value("old-plain@x.com", None) == "old-plain@x.com"


def test_no_kek_passthrough():
    """KEK 未設定なら平文のまま保存（dev / 未構成・後方互換）。"""
    t = EncryptedString(512)
    with patch.dict(os.environ, _env()):
        assert t.process_bind_param("plain@x.com", None) == "plain@x.com"
