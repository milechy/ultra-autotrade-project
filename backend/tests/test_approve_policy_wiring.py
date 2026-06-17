# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_approve_policy_wiring.py
"""approve_proposal エンドポイントが PolicyEngine を呼ぶことを検証するテスト。"""

import os
import tempfile
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-policy-wiring")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@policy-wiring-test.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.policy.engine import PolicyResult  # noqa: E402


@pytest.fixture()
def test_db():
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

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _admin_token(client: TestClient) -> str:
    email = os.environ["INITIAL_ADMIN_EMAIL"]
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpass123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpass123"})
    return r.json()["access_token"]


def _create_pending_proposal(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/proposals",
        json={
            "user_id": 1,
            "operation": "SUPPLY",
            "asset": "USDC",
            "amount": "500.00",
            "amount_usd": "500.00",
            "reason": "test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestApprovePolicyWiring:
    def test_policy_pass_approves_proposal(self, client: TestClient) -> None:
        """PolicyEngine が pass → 提案が approved になる。"""
        token = _admin_token(client)
        pid = _create_pending_proposal(client, token)

        with patch(
            "app.proposals.router.get_policy_engine"
        ) as mock_engine_factory:
            mock_engine = mock_engine_factory.return_value
            mock_engine.check.return_value = PolicyResult(passed=True)

            r = client.post(
                f"/api/proposals/{pid}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        mock_engine.check.assert_called_once()

    def test_policy_violation_returns_422(self, client: TestClient) -> None:
        """PolicyEngine が blocked → 422 POLICY_VIOLATION を返し、status は pending のまま。"""
        token = _admin_token(client)
        pid = _create_pending_proposal(client, token)

        with patch(
            "app.proposals.router.get_policy_engine"
        ) as mock_engine_factory:
            mock_engine = mock_engine_factory.return_value
            mock_engine.check.return_value = PolicyResult(
                passed=False,
                violations=["amount_usd 500 exceeds max_position 100"],
            )

            r = client.post(
                f"/api/proposals/{pid}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 422, r.text
        body = r.json()
        assert body["detail"]["code"] == "POLICY_VIOLATION"
        assert len(body["detail"]["violations"]) == 1

        # status は pending のまま（ロールバックされていること）
        r2 = client.get(
            f"/api/proposals/{pid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.json()["status"] == "pending"

    def test_policy_check_receives_correct_context(self, client: TestClient) -> None:
        """PolicyContext に proposal のフィールドが正しく渡されることを検証。"""
        token = _admin_token(client)
        pid = _create_pending_proposal(client, token)

        captured_ctx = []

        def capture_check(ctx, db):  # type: ignore[no-untyped-def]
            captured_ctx.append(ctx)
            return PolicyResult(passed=True)

        with patch(
            "app.proposals.router.get_policy_engine"
        ) as mock_engine_factory:
            mock_engine = mock_engine_factory.return_value
            mock_engine.check.side_effect = capture_check

            client.post(
                f"/api/proposals/{pid}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert len(captured_ctx) == 1
        ctx = captured_ctx[0]
        assert ctx.asset == "USDC"
        assert ctx.operation == "SUPPLY"
        assert ctx.proposal_id == pid

    def test_hf_violation_blocked(self, client: TestClient) -> None:
        """HF floor 違反も 422 で返ること。"""
        token = _admin_token(client)
        pid = _create_pending_proposal(client, token)

        with patch(
            "app.proposals.router.get_policy_engine"
        ) as mock_engine_factory:
            mock_engine = mock_engine_factory.return_value
            mock_engine.check.return_value = PolicyResult(
                passed=False,
                violations=["expected_hf_after 1.2 below floor 1.5"],
            )

            r = client.post(
                f"/api/proposals/{pid}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 422
        assert "POLICY_VIOLATION" in r.json()["detail"]["code"]
