# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/security/field_crypto.py
"""顧客PII のフィールドレベル暗号化（Track 2 / 層2 暗号化基盤）。

保存時に PII（メールアドレス等）を AES-256-GCM で暗号化し、DB 漏洩時も平文が出ないように
する。検索が必要な列は `blind_index`（HMAC-SHA256・決定的）で等価検索・unique を維持する。

**鍵管理（env KEK + バージョン・ローテ対応）**:
  - ``PII_ENCRYPTION_KEK``       現行 KEK（base64 の 32byte）。暗号化に使う。
  - ``PII_KEK_VERSION``          現行 KEK の版番号（整数・既定 1）。暗号文に埋める。
  - ``PII_ENCRYPTION_KEK_V<n>``  旧版 KEK（ローテ中の復号用・任意）。
  - ``PII_BLIND_INDEX_KEY``      blind index 用 HMAC 鍵（base64・検索列がある場合のみ必須）。
  self-hosted VPS の現実解として env に置く。将来 KMS 移行の余地を残すため版番号を暗号文に
  埋め、旧版鍵での復号を可能にする（HMAC 鍵ローテは blind index 全再計算が必要）。

**暗号文フォーマット**: ``enc:v<version>:<base64(nonce(12B) || ciphertext || tag)>``
  - ``enc:`` prefix が無い値は「未暗号化の平文（レガシー / 未移行）」とみなし、復号側は
    そのまま返す（後方互換・段階移行を可能にする）。

秘密鍵・KEK・平文は**絶対にログに出さない**（CLAUDE.md §Security 1/8）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENC_PREFIX = "enc:"
_NONCE_BYTES = 12  # AES-GCM 推奨 nonce 長
_KEK_BYTES = 32  # AES-256


class FieldCryptoError(RuntimeError):
    """PII 暗号化/復号の構成不備・処理失敗（KEK 未設定・不正フォーマット等）。"""


def _current_version() -> int:
    raw = os.getenv("PII_KEK_VERSION", "1").strip()
    try:
        return int(raw)
    except ValueError:
        return 1


def _load_kek(version: int) -> Optional[bytes]:
    """指定版の KEK（32byte）を env から読む。無ければ None。

    現行版は ``PII_ENCRYPTION_KEK``、旧版は ``PII_ENCRYPTION_KEK_V<n>`` を見る。
    現行版番号が n のとき ``PII_ENCRYPTION_KEK_V<n>`` が無ければ ``PII_ENCRYPTION_KEK``
    にフォールバックする。
    """
    candidates = []
    if version == _current_version():
        candidates.append("PII_ENCRYPTION_KEK")
    candidates.append(f"PII_ENCRYPTION_KEK_V{version}")
    if version == _current_version():
        candidates.append("PII_ENCRYPTION_KEK")  # 明示旧版名が無い場合の保険
    for env_name in candidates:
        raw = os.getenv(env_name, "").strip()
        if raw:
            try:
                key = base64.b64decode(raw)
            except Exception as exc:  # noqa: BLE001
                raise FieldCryptoError(f"{env_name} is not valid base64") from exc
            if len(key) != _KEK_BYTES:
                raise FieldCryptoError(
                    f"{env_name} must decode to {_KEK_BYTES} bytes (got {len(key)})"
                )
            return key
    return None


def is_encryption_configured() -> bool:
    """現行 KEK が設定済みか（未設定なら暗号化せず平文パススルー）。"""
    return _load_kek(_current_version()) is not None


def encrypt_pii(plaintext: Optional[str]) -> Optional[str]:
    """平文 → ``enc:v<ver>:<b64>``。KEK 未設定時は平文をそのまま返す（未移行扱い）。

    None は None のまま返す。既に ``enc:`` 済みの値は二重暗号化しない。
    """
    if plaintext is None:
        return None
    if plaintext.startswith(_ENC_PREFIX):
        return plaintext  # 二重暗号化防止（冪等）
    version = _current_version()
    kek = _load_kek(version)
    if kek is None:
        return plaintext  # KEK 未設定 = 平文パススルー（dev / 未構成）
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(kek).encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = base64.b64encode(nonce + ct).decode("ascii")
    return f"{_ENC_PREFIX}v{version}:{blob}"


def decrypt_pii(stored: Optional[str]) -> Optional[str]:
    """``enc:v<ver>:<b64>`` → 平文。``enc:`` prefix 無しは平文とみなしそのまま返す。

    None は None。版に対応する KEK が無い / 改ざん時は FieldCryptoError。
    """
    if stored is None:
        return None
    if not stored.startswith(_ENC_PREFIX):
        return stored  # レガシー平文（未移行）
    try:
        _, ver_part, blob = stored.split(":", 2)
        version = int(ver_part.lstrip("v"))
    except (ValueError, AttributeError) as exc:
        raise FieldCryptoError("malformed ciphertext header") from exc
    kek = _load_kek(version)
    if kek is None:
        raise FieldCryptoError(f"no KEK available for version {version}")
    try:
        raw = base64.b64decode(blob)
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return AESGCM(kek).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        # 復号失敗（鍵不一致 / 改ざん）。平文・鍵はログに出さない。
        raise FieldCryptoError("PII decryption failed") from exc


def _blind_index_key() -> Optional[bytes]:
    raw = os.getenv("PII_BLIND_INDEX_KEY", "").strip()
    if not raw:
        return None
    try:
        return base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise FieldCryptoError("PII_BLIND_INDEX_KEY is not valid base64") from exc


def blind_index(value: Optional[str]) -> Optional[str]:
    """正規化(小文字化・trim)後の HMAC-SHA256 hex。等価検索・unique 用の決定的インデックス。

    None は None。鍵未設定時は FieldCryptoError（検索列を作るなら鍵は必須）。
    メール等の大文字小文字・前後空白の揺れを吸収して同一値に一致させる。
    """
    if value is None:
        return None
    key = _blind_index_key()
    if key is None:
        raise FieldCryptoError("PII_BLIND_INDEX_KEY is required for blind_index")
    normalized = value.strip().lower().encode("utf-8")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()
