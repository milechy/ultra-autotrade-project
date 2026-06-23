# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/privy_verifier.py
"""Privy ID Token (Auth Token) verifier.

Codex Review P1 (PR #155 / Asana 1214284566521324) 対応。
クライアントから送られてくる Privy DID を素直に保存していたため、
任意の文字列を privy_did として送り込むと別ユーザーの DID を所有しているかのように
登録できた。本モジュールでサーバー側で Privy ID Token を検証し、JWT の sub claim
(= 認証済み DID) と request.privy_did の一致確認を強制する。

Privy 公式仕様 (https://docs.privy.io/authentication/user-authentication/access-tokens):
- 署名アルゴリズム: ES256 (ECDSA P-256)
- iss claim: "privy.io"
- aud claim: Privy App ID
- sub claim: User's Privy DID (例: did:privy:xxxxxxxx)

公開鍵の入手方法 (本実装の優先順):
1. PRIVY_VERIFICATION_KEY 環境変数 (PEM 形式の P-256 公開鍵) — Privy Dashboard
   からコピーする静的キー。HTTP 通信不要・高速・JWKS API 仕様変更の影響なし。
   公式が「重複したリクエストを避けるため Dashboard からキーをコピーする」
   と明示している推奨方式。
2. PRIVY_JWKS_URL (省略時 ``https://auth.privy.io/api/v1/apps/{app_id}/keys``) からの
   動的取得 (1 時間 TTL の in-memory キャッシュ)。鍵ローテーション時にメンテフリーに
   なるが、JWKS endpoint URL は公式ドキュメントに明示されていないため
   フォールバック扱い。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import httpx
import jwt as pyjwt
from fastapi import HTTPException, status
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)
from jwt.algorithms import ECAlgorithm

logger = logging.getLogger(__name__)

PRIVY_ISSUER = "privy.io"
PRIVY_ALGORITHM = "ES256"
DEFAULT_JWKS_URL_TEMPLATE = "https://auth.privy.io/api/v1/apps/{app_id}/keys"
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour


class PrivyVerifier:
    """Privy ID Token (JWT) を検証する。"""

    def __init__(
        self,
        app_id: str,
        verification_key: Optional[str] = None,
        jwks_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        clock_skew_seconds: int = 30,
    ) -> None:
        if not app_id:
            raise ValueError("PrivyVerifier requires non-empty app_id")
        self.app_id = app_id
        self.verification_key = verification_key
        self.jwks_url = jwks_url or DEFAULT_JWKS_URL_TEMPLATE.format(app_id=app_id)
        self._http_client = http_client
        self.clock_skew_seconds = clock_skew_seconds
        self._jwks_cache_keys: dict[str, str] = {}
        self._jwks_cache_fetched_at: float = 0.0
        self._jwks_lock = threading.Lock()

    def verify_id_token(self, token: str) -> str:
        """ID Token を検証して sub claim (Privy DID) を返す。

        失敗時は HTTPException(401) を raise する。JWKS 取得失敗のような
        外部依存系エラーは 503 で返す (クライアント原因と区別するため)。
        """
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty Privy ID token",
            )
        public_key = self._resolve_public_key(token)
        try:
            payload = pyjwt.decode(
                token,
                public_key,
                algorithms=[PRIVY_ALGORITHM],
                audience=self.app_id,
                issuer=PRIVY_ISSUER,
                leeway=self.clock_skew_seconds,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Privy ID token expired",
            ) from exc
        except (InvalidSignatureError, InvalidAudienceError, InvalidIssuerError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Privy ID token",
            ) from exc
        except InvalidTokenError as exc:
            # 期限・aud・iss 以外の構造的エラー (missing claim 等)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Privy ID token",
            ) from exc

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Privy ID token (missing sub)",
            )
        return sub

    # ── 公開鍵解決 ───────────────────────────────────────────

    def _resolve_public_key(self, token: str) -> str:
        if self.verification_key:
            return self.verification_key
        return self._get_jwks_key(token)

    def _get_jwks_key(self, token: str) -> str:
        try:
            unverified_header = pyjwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Privy ID token (header)",
            ) from exc
        kid = unverified_header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Privy ID token (no kid)",
            )

        with self._jwks_lock:
            now = time.time()
            cache_age = now - self._jwks_cache_fetched_at
            if not self._jwks_cache_keys or cache_age >= JWKS_CACHE_TTL_SECONDS:
                self._jwks_cache_keys = self._fetch_jwks()
                self._jwks_cache_fetched_at = now
            elif kid not in self._jwks_cache_keys:
                # キャッシュ TTL 内でも未知の kid なら強制再取得 (key rotation)
                self._jwks_cache_keys = self._fetch_jwks()
                self._jwks_cache_fetched_at = now

            pem = self._jwks_cache_keys.get(kid)

        if pem is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Privy JWKS does not contain kid={kid}",
            )
        return pem

    def _fetch_jwks(self) -> dict[str, str]:
        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=10.0)
        try:
            try:
                resp = client.get(self.jwks_url)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch Privy JWKS from %s: %s", self.jwks_url, exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Privy JWKS unavailable",
                ) from exc
            except ValueError as exc:
                # json.JSONDecodeError も含む。malformed JSON / 空ボディ等の上流不具合
                logger.error("Privy JWKS response is not valid JSON (%s): %s", self.jwks_url, exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Privy JWKS upstream returned invalid JSON",
                ) from exc
        finally:
            if owns_client:
                client.close()

        keys = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(keys, list) or not keys:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Privy JWKS response invalid",
            )
        keys_pem: dict[str, str] = {}
        from cryptography.hazmat.primitives import serialization  # noqa: PLC0415

        for jwk in keys:
            if not isinstance(jwk, dict):
                continue
            kid = jwk.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            try:
                public_key = ECAlgorithm.from_jwk(jwk)
                pem_bytes = public_key.public_bytes(  # type: ignore[union-attr]
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            except (InvalidTokenError, ValueError, TypeError) as exc:
                logger.warning("Skipping invalid Privy JWK kid=%s: %s", kid, exc)
                continue
            keys_pem[kid] = pem_bytes.decode("ascii")
        if not keys_pem:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Privy JWKS response had no usable keys",
            )
        return keys_pem


# ── ファクトリ + シングルトン ─────────────────────────────────────

_default_verifier: Optional[PrivyVerifier] = None
_default_verifier_lock = threading.Lock()


def get_privy_verifier() -> Optional[PrivyVerifier]:
    """環境変数から PrivyVerifier を組み立てる (lazy singleton)。

    PRIVY_APP_ID 未設定なら ``None`` を返し、router 側で
    「Privy 検証 OFF (後方互換モード)」として扱う。
    """
    global _default_verifier
    if _default_verifier is not None:
        return _default_verifier
    with _default_verifier_lock:
        if _default_verifier is not None:
            return _default_verifier
        app_id = os.getenv("PRIVY_APP_ID")
        if not app_id:
            return None
        verification_key = os.getenv("PRIVY_VERIFICATION_KEY") or None
        if verification_key:
            # .env では PEM を 1 行で持つため改行を "\n" リテラルでエスケープしている
            # (例: "-----BEGIN PUBLIC KEY-----\nMFkw...\n-----END PUBLIC KEY-----")。
            # pyjwt/cryptography の PEM パーサは実改行を要求し、リテラル "\n" のままだと
            # `ValueError: Unable to load PEM file` を raise する。これは verify_id_token の
            # except 節 (InvalidTokenError 系) で捕捉されず HTTP 500 になり、かつ
            # verification_key が真値のため JWKS フォールバックにも入らない。
            # ここで実改行へ正規化する (実改行で渡された値には影響しない)。
            verification_key = verification_key.replace("\\n", "\n")
        jwks_url = os.getenv("PRIVY_JWKS_URL") or None
        _default_verifier = PrivyVerifier(
            app_id=app_id,
            verification_key=verification_key,
            jwks_url=jwks_url,
        )
        return _default_verifier


def reset_privy_verifier() -> None:
    """テスト用: グローバルシングルトンをクリア。"""
    global _default_verifier
    with _default_verifier_lock:
        _default_verifier = None
