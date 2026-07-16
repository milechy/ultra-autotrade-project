# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_execute_failure.py
"""_execute_aave_for_proposal の成功/失敗フロー統合テスト。

- Aave 成功 → proposal.status='executed', Transaction(status='completed') 記録
- Aave 失敗 → proposal.status='failed', error_message 記録, Transaction(status='failed') 記録
- 失敗時に Slack 通知が呼ばれることを mock で検証
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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-proposal-failure")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402
from app.transactions.models import Transaction  # noqa: E402

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


def _admin_token(client: TestClient, session_local: object = None) -> str:
    from sqlalchemy.orm import Session

    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    token = r.json()["access_token"]

    # NULL wallet guard: テスト用 admin に wallet_address を設定して実行が通るようにする
    if session_local is not None:
        from app.auth.models import User

        db: Session = session_local()
        try:
            admin = db.query(User).filter(User.email == email).first()
            if admin and not admin.wallet_address:
                admin.wallet_address = "0xTestAdminWallet0000000000000000000000000"
                db.commit()
        finally:
            db.close()

    return token


def _create_proposal(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/proposals",
        json=SAMPLE_PROPOSAL,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def test_aave_execution_success_marks_proposal_executed(client: TestClient, test_db: tuple) -> None:
    """Aave 実行成功 → proposal.status='executed', transaction(status='completed') 記録。

    approve_proposal は is_auto_execution=False 固定（2026-07-16 Step 0）のため、
    Rule8（有効委譲枠必須）の対象外＝delegation grant は不要。
    """
    _override, SessionLocal = test_db
    token = _admin_token(client, SessionLocal)
    proposal_id = _create_proposal(client, token)

    fake_result = AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000.00"),
        tx_hash="0xabcdef1234",
    )

    # AUTO_EXECUTION_ENABLED=true: custodial auto-execution パスを有効化
    with (
        patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "true"}),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=fake_result,
        ),
    ):
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed"
    assert body["tx_hash"] == "0xabcdef1234"
    assert body["error_message"] is None

    db = SessionLocal()
    try:
        proposal = db.scalars(select(Proposal).where(Proposal.id == proposal_id)).first()
        assert proposal is not None
        assert proposal.status == "executed"
        assert proposal.executed_at is not None
        assert proposal.error_message is None

        txs = db.scalars(select(Transaction).where(Transaction.user_id == proposal.user_id)).all()
        assert len(txs) == 1
        assert txs[0].status == "completed"
        assert txs[0].tx_hash == "0xabcdef1234"
        assert txs[0].error_message is None
    finally:
        db.close()


def test_aave_execution_failure_marks_proposal_failed(client: TestClient, test_db: tuple) -> None:
    """Aave 実行失敗 → proposal.status='failed', error_message 記録, transaction(status='failed') 記録。"""
    _override, SessionLocal = test_db
    token = _admin_token(client, SessionLocal)
    proposal_id = _create_proposal(client, token)

    boom = RuntimeError("RPC connection refused")

    # AUTO_EXECUTION_ENABLED=true: custodial auto-execution パスを有効化
    with (
        patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "true"}),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=boom,
        ),
    ):
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert "RPC connection refused" in body["error_message"]
    assert body["tx_hash"] is None

    db = SessionLocal()
    try:
        proposal = db.scalars(select(Proposal).where(Proposal.id == proposal_id)).first()
        assert proposal is not None
        assert proposal.status == "failed"
        assert proposal.error_message is not None
        assert "RPC connection refused" in proposal.error_message
        assert proposal.approved_at is not None
        assert proposal.executed_at is not None
        assert proposal.tx_hash is None

        txs = db.scalars(select(Transaction).where(Transaction.user_id == proposal.user_id)).all()
        assert len(txs) == 1
        failed_tx = txs[0]
        assert failed_tx.status == "failed"
        assert failed_tx.tx_hash is None
        assert failed_tx.error_message is not None
        assert "RPC connection refused" in failed_tx.error_message
    finally:
        db.close()


def test_aave_execution_failure_sends_slack_notification(
    client: TestClient, test_db: tuple
) -> None:
    """Aave 実行失敗時に通知サービスの send() が呼ばれることを検証（mock）。"""
    _override, SessionLocal = test_db
    token = _admin_token(client, SessionLocal)
    proposal_id = _create_proposal(client, token)

    boom = RuntimeError("web3 provider unreachable")

    # AUTO_EXECUTION_ENABLED=true: custodial auto-execution パスを有効化
    with (
        patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "true"}),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=boom,
        ),
        patch("app.notifications.factory.get_notification_service") as mock_get_service,
    ):
        mock_service = mock_get_service.return_value
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert mock_get_service.called
    assert mock_service.send.called

    sent_message = mock_service.send.call_args.args[0]
    assert f"#{proposal_id}" in sent_message.title
    assert "web3 provider unreachable" in sent_message.body
    assert str(proposal_id) in sent_message.body
    assert sent_message.severity.value in ("alert", "emergency")
