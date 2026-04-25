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
        # Aave RPC は tests 環境で未設定のため実行は失敗し "failed" になるが、
        # approve 自体は成功 (approved_at が記録される)。実行成功時は "executed"。
        assert r.json()["status"] in ("approved", "executed", "failed")
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

    def test_admin_can_list_admin_proposals(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/proposals/admin/all", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_admin_can_fetch_admin_stats(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/proposals/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "pending" in data

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


def _create_user_and_login(
    client: TestClient, admin_token: str, role: str, email: str, username: str
) -> str:
    client.post(
        "/users",
        json={"email": email, "username": username, "password": "testpassword123", "role": role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "testpassword123"})
    return r.json()["access_token"]


class TestPartnerProposalBoundaries:
    """partner は他ユーザーの提案を承認・拒否できる。viewer は 403。"""

    def test_partner_can_list_admin_proposals(self, client: TestClient) -> None:
        """partner は GET /api/proposals/admin/all で 200 になる。"""
        admin_token = get_admin_token(client)
        partner_token = _create_user_and_login(
            client, admin_token, "partner", "partner@test.com", "partner"
        )
        r = client.get(
            "/api/proposals/admin/all", headers={"Authorization": f"Bearer {partner_token}"}
        )
        assert r.status_code == 200

    def test_partner_can_fetch_admin_stats(self, client: TestClient) -> None:
        """partner は GET /api/proposals/admin/stats で 200 になる。"""
        admin_token = get_admin_token(client)
        partner_token = _create_user_and_login(
            client, admin_token, "partner", "partner@test.com", "partner"
        )
        r = client.get(
            "/api/proposals/admin/stats", headers={"Authorization": f"Bearer {partner_token}"}
        )
        assert r.status_code == 200
        assert "pending" in r.json()

    def test_viewer_cannot_list_admin_proposals(self, client: TestClient) -> None:
        """viewer は GET /api/proposals/admin/all で 403 になる。"""
        admin_token = get_admin_token(client)
        viewer_token = _create_user_and_login(
            client, admin_token, "viewer", "viewer@test.com", "viewer"
        )
        r = client.get(
            "/api/proposals/admin/all", headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert r.status_code == 403

    def test_partner_can_reject_proposal_for_other_user(self, client: TestClient) -> None:
        """partner は他ユーザー（viewer）の提案を拒否できる。"""
        admin_token = get_admin_token(client)
        # viewer ユーザーを作成して proposal を作成（admin が代理作成）
        viewer_r = client.post(
            "/users",
            json={
                "email": "viewer2@test.com",
                "username": "viewer2",
                "password": "viewerpass123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        viewer_id = viewer_r.json()["id"]
        create_r = client.post(
            "/api/proposals",
            json={**SAMPLE_PROPOSAL, "user_id": viewer_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert create_r.status_code == 201
        proposal_id = create_r.json()["id"]

        partner_token = _create_user_and_login(
            client, admin_token, "partner", "partner@test.com", "partner"
        )
        r = client.post(
            f"/api/proposals/{proposal_id}/reject",
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_partner_can_approve_proposal_for_other_user(self, client: TestClient) -> None:
        """partner は他ユーザーの提案を承認できる（Aave 実行は内部で fail-open）。"""
        admin_token = get_admin_token(client)
        viewer_r = client.post(
            "/users",
            json={
                "email": "viewer3@test.com",
                "username": "viewer3",
                "password": "viewerpass123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        viewer_id = viewer_r.json()["id"]
        create_r = client.post(
            "/api/proposals",
            json={**SAMPLE_PROPOSAL, "user_id": viewer_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert create_r.status_code == 201
        proposal_id = create_r.json()["id"]

        partner_token = _create_user_and_login(
            client, admin_token, "partner", "partner2@test.com", "partner2"
        )
        # Aave 実行は tests 環境で失敗し "failed" に遷移する（approved_at は記録）。
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] in ("approved", "executed", "failed")
        assert r.json()["approved_at"] is not None

    def test_viewer_cannot_approve_proposal(self, client: TestClient) -> None:
        """viewer は POST /api/proposals/{id}/approve で 403 になる。"""
        admin_token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        proposal_id = create_r.json()["id"]
        viewer_token = _create_user_and_login(
            client, admin_token, "viewer", "viewer4@test.com", "viewer4"
        )
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_viewer_cannot_reject_proposal(self, client: TestClient) -> None:
        """viewer は POST /api/proposals/{id}/reject で 403 になる。"""
        admin_token = get_admin_token(client)
        create_r = client.post(
            "/api/proposals",
            json=SAMPLE_PROPOSAL,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        proposal_id = create_r.json()["id"]
        viewer_token = _create_user_and_login(
            client, admin_token, "viewer", "viewer5@test.com", "viewer5"
        )
        r = client.post(
            f"/api/proposals/{proposal_id}/reject",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403
