# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposals_api.py
"""提案APIのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-proposals")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


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


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={
            "email": email,
            "username": "admin",
            "password": "adminpassword123",
        },
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


SAMPLE_PROPOSAL = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "1000.000000000000000000",
    "amount_usd": "1000.00",
    "reason": "AI recommended supply to improve APY",
}


class TestProposalsAPI:
    def test_list_pending_proposals_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/proposals/pending", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_list_pending_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/proposals/pending")
        assert r.status_code == 401

    def test_create_proposal_requires_admin(self, client: TestClient) -> None:
        admin_token = get_admin_token(client)
        client.post(
            "/users",
            json={
                "email": "viewer@test.com",
                "username": "viewer",
                "password": "viewerpassword123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        r = client.post(
            "/auth/login", json={"email": "viewer@test.com", "password": "viewerpassword123"}
        )
        viewer_token = r.json()["access_token"]
        r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_create_proposal_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pending"
        assert data["operation"] == "SUPPLY"

    def test_list_pending_after_create(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/proposals/pending", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_approve_proposal_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        proposal_id = create_r.json()["id"]
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        assert r.json()["approved_at"] is not None

    def test_reject_proposal_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        proposal_id = create_r.json()["id"]
        r = client.post(
            f"/api/proposals/{proposal_id}/reject",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_approve_already_approved_fails(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        proposal_id = create_r.json()["id"]
        client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400

    def test_history_after_approve(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        proposal_id = create_r.json()["id"]
        client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/proposals/history", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_proposal_by_id(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {token}"},
        )
        proposal_id = create_r.json()["id"]
        r = client.get(
            f"/api/proposals/{proposal_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == proposal_id
