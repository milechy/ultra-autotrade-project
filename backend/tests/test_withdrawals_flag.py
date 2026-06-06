# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_withdrawals_flag.py
"""ENABLE_WITHDRAWALS による withdraw EP 配線ガードのテスト。

money を動かす経路のため default-off。
- flag 未設定 / false → route 未登録 → POST /api/users/withdrawals = 404
- flag on (1/true) のときのみ route 登録 → 認証前段に到達 (404 ではない)

★ #391 money gate (staging Sepolia 6 項目) を通すまで本番 .env で true にしないこと。
"""

import os

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-withdrawals-flag")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

_WITHDRAW_PATH = "/api/users/withdrawals"


def test_withdraw_route_404_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # 既定 (env 未設定) では withdraw EP は配線されない → 404
    monkeypatch.delenv("ENABLE_WITHDRAWALS", raising=False)
    client = TestClient(create_app())
    r = client.post(_WITHDRAW_PATH, json={})
    assert r.status_code == 404


def test_withdraw_route_404_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_WITHDRAWALS", "false")
    client = TestClient(create_app())
    r = client.post(_WITHDRAW_PATH, json={})
    assert r.status_code == 404


def test_withdraw_route_registered_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # ENABLE_WITHDRAWALS=1 のときのみ route が登録される。
    # 認証なしの POST は route 存在 → 認証/検証前段に到達するため 404 ではない。
    monkeypatch.setenv("ENABLE_WITHDRAWALS", "1")
    client = TestClient(create_app())
    r = client.post(_WITHDRAW_PATH, json={})
    assert r.status_code != 404
    assert r.status_code in (401, 403, 422)
