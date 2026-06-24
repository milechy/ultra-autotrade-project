# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_portfolio_api.py
"""ポートフォリオ履歴APIのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-portfolio")
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


SAMPLE_SNAPSHOT = {
    "user_id": 1,
    "total_value_usd": "5000.00",
    "total_supply_usd": "5000.00",
    "total_borrow_usd": "0.00",
    "health_factor": "2.5000",
}


class TestPortfolioAPI:
    def test_get_current_no_data(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/portfolio/current", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["has_data"] is False

    def test_get_history_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/portfolio/history", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_history_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/portfolio/history")
        assert r.status_code == 401

    def test_create_snapshot_requires_admin(self, client: TestClient) -> None:
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
            "/api/portfolio/snapshot",
            json=SAMPLE_SNAPSHOT,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_create_snapshot_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.post(
            "/api/portfolio/snapshot",
            json=SAMPLE_SNAPSHOT,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["total_value_usd"] == "5000.00"

    def test_get_current_after_snapshot(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/portfolio/snapshot",
            json=SAMPLE_SNAPSHOT,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/portfolio/current", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["has_data"] is True
        assert data["total_value_usd"] == "5000.00"

    def test_get_history_after_snapshot(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/portfolio/snapshot",
            json=SAMPLE_SNAPSHOT,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/portfolio/history", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_history_period_7d(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/portfolio/snapshot",
            json=SAMPLE_SNAPSHOT,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/portfolio/history?period=7d",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["period"] == "7d"

    def test_weighted_avg_apy_no_data_is_zero(self, client: TestClient) -> None:
        """データ無しのとき weighted_avg_apy = '0.00' (KPI-B)。"""
        token = get_admin_token(client)
        r = client.get("/api/portfolio/current", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["has_data"] is False
        assert data["weighted_avg_apy"] == "0.00"

    def test_weighted_avg_apy_computed(self, client: TestClient) -> None:
        """positions_json の apy_pct を value_usd で加重平均する (KPI-B)。"""
        token = get_admin_token(client)
        snapshot = {
            **SAMPLE_SNAPSHOT,
            "positions_json": [
                {"asset": "USDC", "value_usd": "3000", "apy_pct": "5.0"},
                {"asset": "ETH", "value_usd": "1000", "apy_pct": "9.0"},
            ],
        }
        client.post(
            "/api/portfolio/snapshot",
            json=snapshot,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/portfolio/current", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        # (5*3000 + 9*1000) / 4000 = 24000/4000 = 6.00
        assert data["weighted_avg_apy"] == "6.00"
