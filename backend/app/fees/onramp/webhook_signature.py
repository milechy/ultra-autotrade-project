# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/onramp/webhook_signature.py
"""Stripe webhook 署名 (Stripe-Signature) の HMAC-SHA256 検証 (Phase B-1)。

docs/60_stripe_privy_fiat_onramp_design.md §6 準拠。Stripe SDK 非依存で stdlib
(hmac/hashlib) のみを用い、Stripe 公式の webhook 署名仕様どおりに実装する
(Privy auth_signature と同方針 = 公開仕様の純実装)。

仕様 (Stripe 公式 webhook 署名):
    Header: Stripe-Signature: t=<unix秒>,v1=<HMAC-SHA256 hex>[,v1=...][,v0=...]
    signed_payload = f"{t}.{raw_body}"
    expected      = HMAC_SHA256(key=secret, msg=signed_payload).hexdigest()
    timing-safe compare で v1 のいずれかと一致すれば valid。
    replay 防止: |now - t| <= tolerance (既定 300 秒)。

secret (STRIPE_WEBHOOK_SECRET) は環境変数でのみ管理 (Security Rule 1)。本モジュールは
secret を引数で受け取るだけで env 読取・ログ出力・秘密情報の保持をしない。
現状 dormant: router へは未配線 (Phase C / HUMAN-REVIEW で配線)。
"""

from __future__ import annotations

import hashlib
import hmac

# replay 攻撃防止の既定許容窓 (秒)。Stripe 既定値に合わせる。
DEFAULT_TOLERANCE_SECONDS = 300


class StripeSignatureError(Exception):
    """Stripe-Signature 検証失敗 (フォーマット不正 / 署名不一致 / replay 超過)。"""


def _parse_signature_header(header: str) -> tuple[int, list[str]]:
    """``t=...,v1=...`` をパースして ``(timestamp, [v1 署名...])`` を返す。

    v0 / 他スキームは無視する。t が無い / 整数でない / v1 が無い場合は
    StripeSignatureError を送出する。
    """
    timestamp: int | None = None
    v1_signatures: list[str] = []
    for part in header.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise StripeSignatureError("Stripe-Signature の t が整数でない") from exc
        elif key == "v1":
            v1_signatures.append(value)
    if timestamp is None:
        raise StripeSignatureError("Stripe-Signature に t (timestamp) がない")
    if not v1_signatures:
        raise StripeSignatureError("Stripe-Signature に v1 署名がない")
    return timestamp, v1_signatures


def compute_signature(payload: bytes, secret: str, timestamp: int) -> str:
    """``signed_payload = f"{t}.{raw_body}"`` の HMAC-SHA256 hex を計算する (純関数)。"""
    signed_payload = str(timestamp).encode("utf-8") + b"." + payload
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def verify_stripe_signature(
    *,
    payload: bytes,
    signature_header: str,
    secret: str,
    timestamp_now: int,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> int:
    """Stripe webhook 署名を検証する。成功時は検証済み署名 timestamp を返す。

    :param payload: raw request body (JSON parse 前のバイト列をそのまま渡す)。
    :param signature_header: ``Stripe-Signature`` ヘッダー値。
    :param secret: STRIPE_WEBHOOK_SECRET (呼出側が env から取得して渡す)。
    :param timestamp_now: 現在 unix 秒 (呼出側が time.time() 等で渡す = 純関数化)。
    :param tolerance_seconds: replay 許容窓 (既定 300 秒)。
    :raises StripeSignatureError: 未設定 secret / フォーマット不正 / 署名不一致 / replay 超過。
    :returns: 検証済み署名 timestamp (unix 秒)。
    """
    if not secret:
        raise StripeSignatureError("STRIPE_WEBHOOK_SECRET が未設定 (検証不可)")

    timestamp, v1_signatures = _parse_signature_header(signature_header)

    if abs(timestamp_now - timestamp) > tolerance_seconds:
        raise StripeSignatureError(
            f"Stripe-Signature timestamp が許容窓 {tolerance_seconds}s を超過 (replay 疑い)"
        )

    expected = compute_signature(payload, secret, timestamp)
    if not any(hmac.compare_digest(expected, sig) for sig in v1_signatures):
        raise StripeSignatureError("Stripe-Signature の v1 署名が一致しない")

    return timestamp
