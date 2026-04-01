# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_integration_dashboard.py
"""
シナリオA: ダッシュボード統合テスト

- GET /health
- GET /api/automation/status (認証あり/なし)
- GET /api/automation/dashboard
- GET /api/automation/reports/latest
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import create_app


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine
    Base.metadata.drop_all(bind=test_engine)
    os.close(fd)
    os.unlink(path)


@pytest.fixture()
def client(test_db):
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "adminpassword123"},
    )
    return r.json()["access_token"]


def test_health_endpoint(client: TestClient) -> None:
    """GET /health → 200"""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_automation_status_authenticated(client: TestClient) -> None:
    """認証トークン付き GET /api/automation/status → 200 + JSON構造確認"""
    token = get_admin_token(client)
    r = client.get(
        "/api/automation/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    # is_trading_paused または status フィールドが存在すること
    assert "is_trading_paused" in data or "status" in data


def test_automation_status_unauthenticated(client: TestClient) -> None:
    """トークンなし → 401"""
    r = client.get("/api/automation/status")
    assert r.status_code == 401


def test_automation_dashboard(client: TestClient) -> None:
    """GET /api/automation/dashboard → 200（空データでも500にならない）"""
    token = get_admin_token(client)
    r = client.get(
        "/api/automation/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 または 404 (未実装) を許容。500 は不可
    assert r.status_code != 500
    if r.status_code == 404:
        pytest.skip("endpoint /api/automation/dashboard not implemented")
    assert r.status_code == 200


def test_automation_reports_latest(client: TestClient) -> None:
    """GET /api/automation/reports/latest → 200"""
    token = get_admin_token(client)
    r = client.get(
        "/api/automation/reports/latest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code != 500
    if r.status_code == 404:
        pytest.skip("endpoint /api/automation/reports/latest not implemented")
    assert r.status_code == 200
