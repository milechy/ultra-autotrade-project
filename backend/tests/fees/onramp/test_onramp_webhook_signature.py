# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Stripe webhook 署名検証 (webhook_signature) の単体テスト。

Stripe 公式仕様どおりに HMAC-SHA256 を計算・検証できることを担保する。
秘密鍵・実 Stripe 通信は不要 (純関数 + テスト用 secret)。
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.fees.onramp.webhook_signature import (
    StripeSignatureError,
    compute_signature,
    verify_stripe_signature,
)

_SECRET = "whsec_test_dummy_secret"
_PAYLOAD = b'{"type":"crypto_onramp_session.completed","id":"cos_123"}'
_NOW = 1_700_000_000


def _make_header(payload: bytes, secret: str, timestamp: int) -> str:
    sig = compute_signature(payload, secret, timestamp)
    return f"t={timestamp},v1={sig}"


def test_compute_signature_matches_reference_hmac() -> None:
    """compute_signature が `t.payload` の HMAC-SHA256 hex と一致する。"""
    expected = hmac.new(
        _SECRET.encode(),
        str(_NOW).encode() + b"." + _PAYLOAD,
        hashlib.sha256,
    ).hexdigest()
    assert compute_signature(_PAYLOAD, _SECRET, _NOW) == expected


def test_verify_valid_signature_returns_timestamp() -> None:
    """正しい署名は検証に成功し timestamp を返す。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    assert (
        verify_stripe_signature(
            payload=_PAYLOAD, signature_header=header, secret=_SECRET, timestamp_now=_NOW
        )
        == _NOW
    )


def test_verify_tampered_payload_fails() -> None:
    """payload が改竄されると署名不一致で失敗する。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    with pytest.raises(StripeSignatureError, match="v1 署名が一致しない"):
        verify_stripe_signature(
            payload=_PAYLOAD + b"X",
            signature_header=header,
            secret=_SECRET,
            timestamp_now=_NOW,
        )


def test_verify_wrong_secret_fails() -> None:
    """異なる secret では署名不一致で失敗する。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    with pytest.raises(StripeSignatureError):
        verify_stripe_signature(
            payload=_PAYLOAD,
            signature_header=header,
            secret="whsec_other",
            timestamp_now=_NOW,
        )


def test_verify_replay_outside_tolerance_fails() -> None:
    """許容窓を超えた古い timestamp は replay 疑いで失敗する。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    with pytest.raises(StripeSignatureError, match="replay"):
        verify_stripe_signature(
            payload=_PAYLOAD,
            signature_header=header,
            secret=_SECRET,
            timestamp_now=_NOW + 301,
        )


def test_verify_within_tolerance_passes() -> None:
    """許容窓内 (±300s) の timestamp ズレは許容される。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    assert (
        verify_stripe_signature(
            payload=_PAYLOAD,
            signature_header=header,
            secret=_SECRET,
            timestamp_now=_NOW + 299,
        )
        == _NOW
    )


def test_verify_multiple_v1_one_valid_passes() -> None:
    """複数 v1 のうち 1 つが正しければ検証成功 (Stripe のキーローテーション想定)。"""
    good = compute_signature(_PAYLOAD, _SECRET, _NOW)
    header = f"t={_NOW},v1=deadbeef,v1={good}"
    assert (
        verify_stripe_signature(
            payload=_PAYLOAD, signature_header=header, secret=_SECRET, timestamp_now=_NOW
        )
        == _NOW
    )


def test_verify_empty_secret_raises() -> None:
    """secret 未設定は検証不可で失敗する。"""
    header = _make_header(_PAYLOAD, _SECRET, _NOW)
    with pytest.raises(StripeSignatureError, match="未設定"):
        verify_stripe_signature(
            payload=_PAYLOAD, signature_header=header, secret="", timestamp_now=_NOW
        )


@pytest.mark.parametrize(
    ("header", "match"),
    [
        ("v1=abc", "t .*がない"),
        (f"t={_NOW}", "v1 署名がない"),
        ("t=notanint,v1=abc", "整数でない"),
        ("", "t .*がない"),
    ],
)
def test_verify_malformed_header_raises(header: str, match: str) -> None:
    """フォーマット不正な Stripe-Signature ヘッダーは StripeSignatureError。"""
    with pytest.raises(StripeSignatureError, match=match):
        verify_stripe_signature(
            payload=_PAYLOAD, signature_header=header, secret=_SECRET, timestamp_now=_NOW
        )
