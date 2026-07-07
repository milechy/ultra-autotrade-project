# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/security/sqlalchemy_types.py
"""PII フィールド暗号化用の SQLAlchemy TypeDecorator（Track 2 / 層2）。

`EncryptedString` を列型に使うと、ORM の write 時に `encrypt_pii`、read 時に `decrypt_pii`
が透過的に走る。呼び出し側（router / service）は平文を扱うだけで、DB には暗号文が入る。
各読み書き箇所を個別に触らないため、暗号化漏れ（= 平文がそのまま保存される事故）を防ぐ。

後方互換: `enc:` prefix の無い既存平文はそのまま読める（段階移行を許容）。KEK 未設定の
環境（dev / 未構成）では平文パススルー（`field_crypto` 参照）。

DB カラム長: 暗号文は base64 で平文より長い。列は十分な長さ（例: String(512) / Text）で
定義すること。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.security.field_crypto import decrypt_pii, encrypt_pii


class EncryptedString(TypeDecorator[str]):
    """保存時に暗号化・取得時に復号する文字列型（AES-256-GCM / `field_crypto`）。

    検索（WHERE 等価）が不要な PII 列に使う。等価検索が要る列は別途 blind index 列を
    併設すること（`field_crypto.blind_index`）。
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect: object) -> Optional[str]:
        return encrypt_pii(value)

    def process_result_value(self, value: Optional[str], dialect: object) -> Optional[str]:
        return decrypt_pii(value)
