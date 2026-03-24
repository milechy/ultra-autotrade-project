# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_transactions_api.py
"""取引履歴APIのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-transactions")
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


SAMPLE_TX = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "1000.000000000000000000",
    "amount_usd": "1000.00",
    "chain": "arbitrum_one",
    "status": "success",
}


class TestTransactionsAPI:
    def test_list_transactions_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_list_transactions_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/transactions")
        assert r.status_code == 401

    def test_create_transaction_requires_admin(self, client: TestClient) -> None:
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
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_create_transaction_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["operation"] == "SUPPLY"
        assert data["asset"] == "USDC"

    def test_list_transactions_after_create(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_transaction_by_id(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        tx_id = create_r.json()["id"]
        r = client.get(f"/api/transactions/{tx_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["id"] == tx_id

    def test_get_transaction_not_found(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions/9999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_transaction_stats_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_count"] == 0
        assert data["success_count"] == 0

    def test_transaction_stats_with_data(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/transactions/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_count"] == 1
        assert data["success_count"] == 1

    def test_admin_list_all_transactions(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/admin/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_filter_by_operation(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?operation=SUPPLY",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["operation"] == "SUPPLY" for item in r.json()["items"])

    def test_filter_by_status(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?tx_status=success",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["status"] == "success" for item in r.json()["items"])

    def test_filter_by_chain(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?chain=arbitrum_one",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["chain"] == "arbitrum_one" for item in r.json()["items"])
