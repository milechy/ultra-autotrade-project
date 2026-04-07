# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_accuracy_api.py
"""AI的中率APIエンドポイントのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-accuracy-api")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "accuracy_api_admin@example.com")

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


def get_viewer_token(client: TestClient) -> str:
    admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "accuracy_api_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": admin_email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": admin_email, "password": "adminpassword123"})
    return r.json()["access_token"]


class TestAccuracyAPI:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/ai/accuracy")
        assert r.status_code == 401

    def test_empty_returns_zeros(self, client: TestClient) -> None:
        token = get_viewer_token(client)
        r = client.get("/api/ai/accuracy", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_decisions"] == 0
        assert data["correct_count"] == 0
        assert data["accuracy_pct"] == "0.00"
        assert data["last_30d_accuracy_pct"] == "0.00"
        assert "BUY" in data["by_action"]
        assert "SELL" in data["by_action"]

    def test_with_decisions(self, client: TestClient) -> None:
        token = get_viewer_token(client)
        # Create decisions via the admin decisions API
        for payload in [
            {
                "query": "q",
                "action": "BUY",
                "confidence": 70,
                "primary_provider": "claude",
                "primary_action": "BUY",
                "primary_confidence": 70,
                "agreed": True,
            },
            {
                "query": "q",
                "action": "SELL",
                "confidence": 60,
                "primary_provider": "claude",
                "primary_action": "SELL",
                "primary_confidence": 60,
                "agreed": False,
            },
            {
                "query": "q",
                "action": "HOLD",
                "confidence": 50,
                "primary_provider": "claude",
                "primary_action": "HOLD",
                "primary_confidence": 50,
                "agreed": True,
            },
        ]:
            client.post(
                "/api/ai/decisions",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

        r = client.get("/api/ai/accuracy", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        # BUY(agreed)+SELL(!agreed) = 2 total, 1 correct
        assert data["total_decisions"] == 2
        assert data["correct_count"] == 1
        assert data["accuracy_pct"] == "50.00"
        assert data["by_action"]["BUY"]["total"] == 1
        assert data["by_action"]["BUY"]["correct"] == 1
        assert data["by_action"]["SELL"]["total"] == 1
        assert data["by_action"]["SELL"]["correct"] == 0

    def test_days_param(self, client: TestClient) -> None:
        token = get_viewer_token(client)
        r = client.get("/api/ai/accuracy?days=30", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "total_decisions" in data
