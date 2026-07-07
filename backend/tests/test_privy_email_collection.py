# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_email_collection.py
"""Privy linked_accounts からの email 抽出（Track 2 層1 / dormant 収集）の単体テスト。

`extract_email_from_claims`（純関数）と `verify_id_token_with_email`（_verify_and_decode を
mock）を検証する。実 JWT / 実 Privy は使わない。
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from app.auth.privy_verifier import PrivyVerifier, extract_email_from_claims

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-privy-email")


# ---------------------------------------------------------------------------
# extract_email_from_claims
# ---------------------------------------------------------------------------


def test_extract_email_from_list():
    payload = {
        "sub": "did:privy:abc",
        "linked_accounts": [
            {"type": "wallet", "address": "0xabc"},
            {"type": "email", "address": "user@example.com"},
        ],
    }
    assert extract_email_from_claims(payload) == "user@example.com"


def test_extract_email_from_json_string():
    """linked_accounts が JSON 文字列でも抽出できる。"""
    payload = {
        "sub": "did:privy:abc",
        "linked_accounts": json.dumps([{"type": "email", "address": "  Str@X.com "}]),
    }
    assert extract_email_from_claims(payload) == "Str@X.com"  # trim される


def test_extract_email_none_when_no_linked_accounts():
    assert extract_email_from_claims({"sub": "did:privy:abc"}) is None


def test_extract_email_none_when_no_email_type():
    payload = {"linked_accounts": [{"type": "wallet", "address": "0xabc"}]}
    assert extract_email_from_claims(payload) is None


def test_extract_email_malformed_returns_none():
    assert extract_email_from_claims({"linked_accounts": "not-json{"}) is None
    assert extract_email_from_claims({"linked_accounts": 123}) is None
    assert extract_email_from_claims({"linked_accounts": [{"type": "email"}]}) is None


# ---------------------------------------------------------------------------
# verify_id_token_with_email
# ---------------------------------------------------------------------------


def test_verify_with_email_returns_did_and_email():
    v = PrivyVerifier(app_id="app-123", verification_key="dummy")
    payload = {
        "sub": "did:privy:xyz",
        "linked_accounts": [{"type": "email", "address": "a@b.com"}],
    }
    with patch.object(v, "_verify_and_decode", return_value=payload):
        did, email = v.verify_id_token_with_email("tok")
    assert did == "did:privy:xyz"
    assert email == "a@b.com"


def test_verify_with_email_none_when_wallet_only():
    v = PrivyVerifier(app_id="app-123", verification_key="dummy")
    payload = {"sub": "did:privy:xyz", "linked_accounts": [{"type": "wallet", "address": "0x1"}]}
    with patch.object(v, "_verify_and_decode", return_value=payload):
        did, email = v.verify_id_token_with_email("tok")
    assert did == "did:privy:xyz"
    assert email is None


def test_verify_id_token_still_returns_sub():
    """既存 verify_id_token は従来通り sub のみ返す(回帰)。"""
    v = PrivyVerifier(app_id="app-123", verification_key="dummy")
    with patch.object(v, "_verify_and_decode", return_value={"sub": "did:privy:z"}):
        assert v.verify_id_token("tok") == "did:privy:z"
