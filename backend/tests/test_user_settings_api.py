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
        """GET /auth/me レスポンスに execution_policy が含まれること。

        P3-1: 新規ユーザーの execution_policy safe default は require_approval。
        """
        token = register_and_login(client)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "execution_policy" in data
        assert data["execution_policy"] == "require_approval"

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

    def test_terms_agreed_at_null_by_default(self, client: TestClient) -> None:
        """GET /api/user/settings で terms_agreed_at が初期状態では null であること。"""
        token = register_and_login(client)
        r = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "terms_agreed_at" in data
        # 新規ユーザーは同意未完了
        assert data["terms_agreed_at"] is None

    def test_terms_agree_records_timestamp(self, client: TestClient) -> None:
        """POST /api/user/terms-agree で terms_agreed_at が記録されること。"""
        token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # 同意前: terms_agreed_at is null
        settings_before = client.get("/api/user/settings", headers=headers)
        assert settings_before.json()["terms_agreed_at"] is None

        # 同意
        r = client.post("/api/user/terms-agree", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "terms_agreed_at" in data
        assert data["terms_agreed_at"] is not None
        assert data["already_agreed"] is False

        # 同意後: settings に terms_agreed_at が反映されること
        settings_after = client.get("/api/user/settings", headers=headers)
        assert settings_after.json()["terms_agreed_at"] is not None

    def test_terms_agree_idempotent(self, client: TestClient) -> None:
        """POST /api/user/terms-agree は冪等で、再実行しても already_agreed=True が返ること。"""
        token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # 1回目
        r1 = client.post("/api/user/terms-agree", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["already_agreed"] is False

        # 2回目: 冪等
        r2 = client.post("/api/user/terms-agree", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["already_agreed"] is True
        # タイムスタンプは 1 回目と同じ（秒レベルで一致）
        ts1 = r1.json()["terms_agreed_at"][:19]  # "YYYY-MM-DDTHH:MM:SS"
        ts2 = r2.json()["terms_agreed_at"][:19]
        assert ts1 == ts2

    def test_terms_agree_requires_auth(self, client: TestClient) -> None:
        """POST /api/user/terms-agree は認証必須であること。"""
        r = client.post("/api/user/terms-agree")
        assert r.status_code == 401
