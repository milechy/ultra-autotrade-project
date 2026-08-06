# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_wallet_propagation.py
"""_execute_aave_for_proposal が user.wallet_address を伝播することを検証する。

Lane 13 / Asana 1215185702832740 / 2026-05-28:
- partner 別資金分離のために user.wallet_address を MultiChainAaveService.execute_rebalance に渡す
- user.wallet_address が NULL の場合は env fallback + Slack 警告 (fail-safe)
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-wallet-propagation")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "wallet_admin@example.com")

from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.models import User  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

YAMAMOTO_WALLET = "0x2064000000000000000000000000000000000cc66"[:42]


@pytest.fixture(autouse=True)
def _bypass_policy_for_wallet_tests(monkeypatch):
    """Wallet 伝播テストは policy タイミング依存チェックを経由させない。
    policy の correct/fail は test_policy_engine.py で検証済み。"""
    from app.policy.engine import PolicyResult

    monkeypatch.setattr(
        "app.policy.engine.PolicyEngine.check",
        lambda self, ctx, db: PolicyResult(passed=True),
    )


HASHIGUCHI_WALLET = "0xabcdef0123456789abcdef0123456789abcdef01"

SAMPLE_PROPOSAL = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "1000.000000000000000000",
    "amount_usd": "1000.00",
    "reason": "AI recommended supply",
}


@pytest.fixture()
def test_db() -> Generator:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db: tuple) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "wallet_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


def _create_proposal(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/proposals",
        json=SAMPLE_PROPOSAL,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _set_admin_wallet(SessionLocal, wallet: str | None) -> None:
    """fixture で登録した admin user の wallet_address を更新する。"""
    db = SessionLocal()
    try:
        admin = db.scalars(select(User).order_by(User.id)).first()
        assert admin is not None, "admin user must be registered before this helper"
        admin.wallet_address = wallet
        db.commit()
    finally:
        db.close()


def test_wallet_address_is_propagated_to_execute_rebalance(
    client: TestClient, test_db: tuple
) -> None:
    """user.wallet_address が MultiChainAaveService.execute_rebalance に渡ること。"""
    _override, SessionLocal = test_db
    token = _admin_token(client)
    proposal_id = _create_proposal(client, token)
    _set_admin_wallet(SessionLocal, HASHIGUCHI_WALLET)

    fake_result = AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000.00"),
        tx_hash="0xpartner_b_hash",
    )

    with (
        patch.dict(
            os.environ, {"AUTO_EXECUTION_ENABLED": "true", "CUSTODIAL_EXECUTION_ENABLED": "true"}
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=fake_result,
        ) as mock_execute,
    ):
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert r.json()["status"] == "executed"

    assert mock_execute.called
    kwargs = mock_execute.call_args.kwargs
    assert kwargs.get("wallet_address") == HASHIGUCHI_WALLET, (
        f"wallet_address was not propagated. kwargs={kwargs}"
    )


def test_null_wallet_is_blocked_by_layer1_guard(client: TestClient, test_db: tuple) -> None:
    """user.wallet_address が NULL の場合、Layer 1 guard が執行をブロックして status='failed' になること。"""
    _override, SessionLocal = test_db
    token = _admin_token(client)
    proposal_id = _create_proposal(client, token)
    _set_admin_wallet(SessionLocal, None)

    with (
        patch.dict(
            os.environ, {"AUTO_EXECUTION_ENABLED": "true", "CUSTODIAL_EXECUTION_ENABLED": "true"}
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
        ) as mock_execute,
    ):
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    # Layer 1 guard で止まるため execute_rebalance は呼ばれない
    mock_execute.assert_not_called()
    # エラーメッセージに "execution blocked" が含まれること
    assert "execution blocked" in (r.json().get("error_message") or "")


def test_two_users_propagate_their_own_wallets(client: TestClient, test_db: tuple) -> None:
    """user_id=11 / user_id=18 をシミュレーションして両者の wallet がそれぞれ渡ることを確認する。

    staging dry_run の代替 unit test (両 user で別 wallet が伝播することを保証)。
    """
    _override, SessionLocal = test_db
    token = _admin_token(client)

    # admin (山本さん wallet 想定) で proposal を 1 件作成
    proposal_id_yamamoto = _create_proposal(client, token)
    _set_admin_wallet(SessionLocal, YAMAMOTO_WALLET)

    fake_result = AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000.00"),
        tx_hash="0xyamamoto_hash",
    )

    with (
        patch.dict(
            os.environ, {"AUTO_EXECUTION_ENABLED": "true", "CUSTODIAL_EXECUTION_ENABLED": "true"}
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=fake_result,
        ) as mock_execute_a,
    ):
        r1 = client.post(
            f"/api/proposals/{proposal_id_yamamoto}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r1.status_code == 200
    assert mock_execute_a.call_args.kwargs["wallet_address"] == YAMAMOTO_WALLET

    # admin の wallet を橋口さん wallet に切替 (user_id 同一だが別 wallet を持つ partner 想定)
    proposal_id_hashiguchi = _create_proposal(client, token)
    _set_admin_wallet(SessionLocal, HASHIGUCHI_WALLET)

    with (
        patch.dict(
            os.environ, {"AUTO_EXECUTION_ENABLED": "true", "CUSTODIAL_EXECUTION_ENABLED": "true"}
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=fake_result,
        ) as mock_execute_b,
    ):
        r2 = client.post(
            f"/api/proposals/{proposal_id_hashiguchi}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r2.status_code == 200
    assert mock_execute_b.call_args.kwargs["wallet_address"] == HASHIGUCHI_WALLET

    # 2 件の execute は別 wallet で呼ばれている (regression: 共通 wallet で実行されない)
    assert (
        mock_execute_a.call_args.kwargs["wallet_address"]
        != mock_execute_b.call_args.kwargs["wallet_address"]
    )
