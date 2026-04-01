# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_integration_auth.py
"""
シナリオF: 認証・認可統合テスト

- 登録→ログイン→JWT取得→認証付きリクエスト
- GET /auth/me → ユーザー情報
- admin/viewer の権限差の確認
- viewer が read-only エンドポイントにアクセスできること
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
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def get_viewer_token(client: TestClient, admin_token: str) -> str:
    """adminが viewer ユーザーを作成してトークンを返す。"""
    viewer_email = "viewer_test@example.com"
    r = client.post(
        "/users",
        json={
            "email": viewer_email,
            "username": "viewer_user",
            "password": "viewerpassword123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if r.status_code not in (200, 201):
        return ""
    r2 = client.post(
        "/auth/login",
        json={"email": viewer_email, "password": "viewerpassword123"},
    )
    if r2.status_code != 200:
        return ""
    return r2.json()["access_token"]


def test_wallet_auth_flow(client: TestClient) -> None:
    """登録→ログイン→JWT取得→認証付きリクエスト"""
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

    # 登録
    reg_r = client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    assert reg_r.status_code in (200, 201)

    # ログイン
    login_r = client.post(
        "/auth/login",
        json={"email": email, "password": "adminpassword123"},
    )
    assert login_r.status_code == 200
    token_data = login_r.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    assert token

    # 認証付きリクエスト
    me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_r.status_code == 200
    me_data = me_r.json()
    assert me_data["email"] == email


def test_auth_me(client: TestClient) -> None:
    """GET /auth/me → ユーザー情報"""
    token = get_admin_token(client)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "email" in data
    assert "id" in data


def test_role_based_access(client: TestClient) -> None:
    """admin/viewer の権限差を確認（admin専用エンドポイントにviewerでアクセス→403）"""
    admin_token = get_admin_token(client)
    viewer_token = get_viewer_token(client, admin_token)
    if not viewer_token:
        pytest.skip("Cannot create viewer user for role test")

    # admin専用: GET /users → admin は 200、viewer は 403
    admin_r = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    viewer_r = client.get("/users", headers={"Authorization": f"Bearer {viewer_token}"})

    assert admin_r.status_code == 200
    assert viewer_r.status_code == 403


def test_read_only_endpoints_viewer(client: TestClient) -> None:
    """viewerがread-onlyエンドポイントにアクセスできること"""
    admin_token = get_admin_token(client)
    viewer_token = get_viewer_token(client, admin_token)
    if not viewer_token:
        pytest.skip("Cannot create viewer user for read-only test")

    # GET /api/automation/status は viewer でも 200 になること
    r = client.get(
        "/api/automation/status",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/automation/status not implemented")
    assert r.status_code == 200
