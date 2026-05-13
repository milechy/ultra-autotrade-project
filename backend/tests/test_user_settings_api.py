# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_user_settings_api.py
"""ユーザー設定APIのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-settings")
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


def register_and_login(
    client: TestClient,
    email: str | None = None,
    username: str = "testuser",
    password: str = "userpassword123",
) -> str:
    if email is None:
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
        },
    )
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


class TestUserSettingsAPI:
    def test_get_settings_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/user/settings")
        assert r.status_code == 401

    def test_get_settings_default(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["notification_frequency"] == "important"
        assert data["notification_email"] is None

    def test_update_notification_email(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"notification_email": "notify@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["notification_email"] == "notify@example.com"

    def test_update_notification_frequency(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"notification_frequency": "all"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["notification_frequency"] == "all"

    def test_update_max_single_trade_usd(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"max_single_trade_usd": "500.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert float(r.json()["max_single_trade_usd"]) == 500.0

    def test_update_invalid_frequency(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"notification_frequency": "never"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_pause_user(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.post("/api/user/pause", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_resume_user(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.post("/api/user/resume", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_automation_pause(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.post("/api/automation/pause", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_automation_resume(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.post("/api/automation/resume", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_update_execution_policy_require_approval(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"execution_policy": "require_approval"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "require_approval"

    def test_update_execution_policy_auto_execute(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"execution_policy": "auto_execute"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "auto_execute"

    def test_update_execution_policy_proposal_only(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"execution_policy": "proposal_only"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "proposal_only"

    def test_update_execution_policy_invalid(self, client: TestClient) -> None:
        token = register_and_login(client)
        r = client.put(
            "/api/user/settings",
            json={"execution_policy": "invalid_policy"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_execution_policy_in_response(self, client: TestClient) -> None:
        """GET /settings レスポンスに execution_policy が含まれること。"""
        token = register_and_login(client)
        r = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "execution_policy" in r.json()

    def test_get_me_includes_execution_policy(self, client: TestClient) -> None:
        """GET /auth/me レスポンスに execution_policy が含まれること。"""
        token = register_and_login(client)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "execution_policy" in data
        assert data["execution_policy"] == "auto_execute"

    def test_get_me_execution_policy_reflects_update(self, client: TestClient) -> None:
        """/api/user/settings で execution_policy を更新後、/auth/me に反映されること。"""
        token = register_and_login(client)
        # require_approval に更新
        put_r = client.put(
            "/api/user/settings",
            json={"execution_policy": "require_approval"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert put_r.status_code == 200
        # /auth/me で確認
        me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_r.status_code == 200
        assert me_r.json()["execution_policy"] == "require_approval"
