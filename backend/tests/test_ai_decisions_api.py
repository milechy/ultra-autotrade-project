# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_decisions_api.py
"""AI判定履歴APIのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ai-decisions")
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


SAMPLE_DECISION = {
    "query": "BTC price trend analysis",
    "action": "HOLD",
    "confidence": 72,
    "reason": "Market uncertain",
    "primary_provider": "claude",
    "primary_action": "HOLD",
    "primary_confidence": 72,
    "agreed": True,
}


class TestAIDecisionsAPI:
    def test_list_decisions_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/ai/decisions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_decisions_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/ai/decisions")
        assert r.status_code == 401

    def test_create_decision_requires_admin(self, client: TestClient) -> None:
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
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_create_decision_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["action"] == "HOLD"
        assert data["confidence"] == 72
        assert "id" in data

    def test_list_decisions_after_create(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/ai/decisions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_get_decision_by_id(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        decision_id = create_r.json()["id"]
        r = client.get(
            f"/api/ai/decisions/{decision_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == decision_id

    def test_get_decision_not_found(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/ai/decisions/9999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_get_latest_decision(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/ai/decisions/latest", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["action"] == "HOLD"

    def test_get_latest_decision_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/ai/decisions/latest", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_filter_by_action(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        buy_decision = {**SAMPLE_DECISION, "action": "BUY", "primary_action": "BUY"}
        client.post(
            "/api/ai/decisions",
            json=buy_decision,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/ai/decisions?action=HOLD",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert all(item["action"] == "HOLD" for item in data["items"])

    def test_filter_by_min_confidence(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/ai/decisions?min_confidence=80",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert all(item["confidence"] >= 80 for item in data["items"])

    def test_filter_by_agreed(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/ai/decisions",
            json=SAMPLE_DECISION,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/ai/decisions?agreed=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert all(item["agreed"] for item in data["items"])
