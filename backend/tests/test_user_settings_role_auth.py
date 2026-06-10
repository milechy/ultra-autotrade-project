# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_user_settings_role_auth.py
"""user_mode / execution_policy 変更の RBAC テスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-role-auth")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ADMIN_EMAIL = "admin_role_auth@example.com"
_ADMIN_PASSWORD = "adminpassword123"


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
    os.environ["INITIAL_ADMIN_EMAIL"] = _ADMIN_EMAIL
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_admin(client: TestClient) -> str:
    """admin ユーザーを登録してトークンを返す。"""
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "admin_role_auth", "password": _ADMIN_PASSWORD},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


def _create_user_with_role(client: TestClient, admin_token: str, email: str, role: str) -> str:
    """admin が指定ロールのユーザーを作成し、そのユーザーのトークンを返す。"""
    r = client.post(
        "/users",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "password123",
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), f"User creation failed for {email}: {r.text}"
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_partner_can_update_user_mode(client: TestClient) -> None:
    """partnerロールは user_mode=managed（execution_policy=auto_execute）に変更できること。"""
    admin_token = _register_admin(client)
    token = _create_user_with_role(client, admin_token, "partner_mode@example.com", "partner")

    r = client.put(
        "/api/user/settings",
        json={"user_mode": "managed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["user_mode"] == "managed"
    assert data["execution_policy"] == "auto_execute"


def test_partner_can_revert_to_active(client: TestClient) -> None:
    """partnerロールは user_mode=active（execution_policy=require_approval）に戻せること。"""
    admin_token = _register_admin(client)
    token = _create_user_with_role(client, admin_token, "partner_active@example.com", "partner")

    r = client.put(
        "/api/user/settings",
        json={"user_mode": "active"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["execution_policy"] == "require_approval"


def test_viewer_can_update_user_mode(client: TestClient) -> None:
    """viewerロールも user_mode を本人セルフサービスで変更できること。

    LIFF 運用モード画面でエンドユーザー（viewer）が「完全おまかせ(managed)/
    アクティブ(active)」を自分で切り替えられる必要があるため、user_mode 変更は
    role 制限なし。execution_policy も user_mode に追従して更新される。
    """
    admin_token = _register_admin(client)
    token = _create_user_with_role(client, admin_token, "viewer_mode@example.com", "viewer")

    # active へ切替
    r = client.put(
        "/api/user/settings",
        json={"user_mode": "active"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user_mode"] == "active"
    assert data["execution_policy"] == "require_approval"

    # managed（完全おまかせ = auto_execute）へも切替可能
    r = client.put(
        "/api/user/settings",
        json={"user_mode": "managed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["execution_policy"] == "auto_execute"


def test_viewer_cannot_update_execution_policy_directly(client: TestClient) -> None:
    """viewerロールは execution_policy を直接変更しようとしても 403 になること。"""
    admin_token = _register_admin(client)
    token = _create_user_with_role(client, admin_token, "viewer_policy@example.com", "viewer")

    r = client.put(
        "/api/user/settings",
        json={"execution_policy": "auto_execute"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_admin_can_update_user_mode(client: TestClient) -> None:
    """adminロールは user_mode 変更が許可されること。"""
    token = _register_admin(client)

    r = client.put(
        "/api/user/settings",
        json={"user_mode": "active"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["execution_policy"] == "require_approval"


def test_viewer_can_update_non_policy_settings(client: TestClient) -> None:
    """viewerロールは execution_policy 以外の設定（通知頻度等）は変更できること。"""
    admin_token = _register_admin(client)
    token = _create_user_with_role(client, admin_token, "viewer_notif@example.com", "viewer")

    r = client.put(
        "/api/user/settings",
        json={"notification_frequency": "all"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["notification_frequency"] == "all"
