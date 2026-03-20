# backend/tests/test_auth_rbac.py
"""
RBAC 境界テスト。

- Viewer ロールの権限境界
- Editor ロールの権限境界
- Admin ロールのフルアクセス確認
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# テスト用環境変数を設定
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-rbac-tests"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"

from app.database import Base, get_db
from app.main import create_app


@pytest.fixture()
def test_db():
    """テスト用の一時的な SQLite データベースを作成する。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Generator:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine

    Base.metadata.drop_all(bind=test_engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    """テスト用クライアントを作成する。"""
    override_get_db, _ = test_db
    os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_admin(client: TestClient) -> str:
    """admin ユーザーを登録してトークンを返す。"""
    client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "username": "admin",
            "password": "adminpassword123",
        },
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "adminpassword123"},
    )
    return login_response.json()["access_token"]


def _create_user_and_login(
    client: TestClient,
    admin_token: str,
    email: str,
    username: str,
    role: str,
) -> tuple[str, int]:
    """指定ロールのユーザーを作成してトークンとユーザーIDを返す。"""
    create_response = client.post(
        "/users",
        json={
            "email": email,
            "username": username,
            "password": "password123",
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = create_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_response.json()["access_token"]
    return token, user_id


class TestViewerPermissions:
    """Viewer ロールの権限境界テスト。"""

    def _setup(self, client: TestClient) -> tuple[str, int]:
        """admin を登録し viewer を作成してトークンと ID を返す。"""
        admin_token = _register_admin(client)
        viewer_token, viewer_id = _create_user_and_login(
            client, admin_token, "viewer@example.com", "viewer", "viewer"
        )
        return viewer_token, viewer_id

    def test_viewer_can_get_own_profile(self, client: TestClient) -> None:
        """Viewer は GET /auth/me で自分のプロフィールを取得できる。"""
        viewer_token, _ = self._setup(client)
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "viewer@example.com"
        assert data["role"] == "viewer"

    def test_viewer_cannot_list_all_users(self, client: TestClient) -> None:
        """Viewer は GET /users で 403 になる。"""
        viewer_token, _ = self._setup(client)
        response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_viewer_cannot_create_user(self, client: TestClient) -> None:
        """Viewer は POST /users で 403 になる。"""
        viewer_token, _ = self._setup(client)
        response = client.post(
            "/users",
            json={
                "email": "another@example.com",
                "username": "another",
                "password": "password123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_viewer_cannot_delete_user(self, client: TestClient) -> None:
        """Viewer は DELETE /users/{id} で 403 になる。"""
        admin_token = _register_admin(client)
        viewer_token, viewer_id = _create_user_and_login(
            client, admin_token, "viewer@example.com", "viewer", "viewer"
        )
        # Viewer が自分自身を削除しようとしても admin 権限がないので 403
        response = client.delete(
            f"/users/{viewer_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_viewer_can_get_own_user_detail(self, client: TestClient) -> None:
        """Viewer は GET /users/{own_id} で自分の詳細を取得できる。"""
        viewer_token, viewer_id = self._setup(client)
        response = client.get(
            f"/users/{viewer_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == viewer_id
        assert data["email"] == "viewer@example.com"

    def test_viewer_cannot_change_own_role(self, client: TestClient) -> None:
        """Viewer は PUT /users/{own_id} で role を変更しようとすると 403 になる。"""
        viewer_token, viewer_id = self._setup(client)
        response = client.put(
            f"/users/{viewer_id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_viewer_can_change_own_password(self, client: TestClient) -> None:
        """Viewer は POST /auth/change-password で自分のパスワードを変更できる。"""
        viewer_token, _ = self._setup(client)
        response = client.post(
            "/auth/change-password",
            json={
                "current_password": "password123",
                "new_password": "newpassword456",
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 204


class TestEditorPermissions:
    """Editor ロールの権限境界テスト。"""

    def _setup(self, client: TestClient) -> tuple[str, int]:
        """admin を登録し editor を作成してトークンと ID を返す。"""
        admin_token = _register_admin(client)
        editor_token, editor_id = _create_user_and_login(
            client, admin_token, "editor@example.com", "editor", "editor"
        )
        return editor_token, editor_id

    def test_editor_cannot_list_all_users(self, client: TestClient) -> None:
        """Editor は GET /users で 403 になる。"""
        editor_token, _ = self._setup(client)
        response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert response.status_code == 403

    def test_editor_cannot_create_user(self, client: TestClient) -> None:
        """Editor は POST /users で 403 になる。"""
        editor_token, _ = self._setup(client)
        response = client.post(
            "/users",
            json={
                "email": "another@example.com",
                "username": "another",
                "password": "password123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert response.status_code == 403

    def test_editor_can_get_own_profile(self, client: TestClient) -> None:
        """Editor は GET /auth/me で自分のプロフィールを取得できる。"""
        editor_token, _ = self._setup(client)
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "editor@example.com"
        assert data["role"] == "editor"


class TestAdminPermissions:
    """Admin ロールのフルアクセステスト。"""

    def test_admin_can_list_all_users(self, client: TestClient) -> None:
        """Admin は GET /users でユーザー一覧を取得できる。"""
        admin_token = _register_admin(client)
        response = client.get(
            "/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        assert len(users) >= 1

    def test_admin_can_create_user(self, client: TestClient) -> None:
        """Admin は POST /users で新しいユーザーを作成できる。"""
        admin_token = _register_admin(client)
        response = client.post(
            "/users",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "password123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "viewer"

    def test_admin_can_update_any_user(self, client: TestClient) -> None:
        """Admin は PUT /users/{id} で任意のユーザーを更新できる。"""
        admin_token = _register_admin(client)
        _, viewer_id = _create_user_and_login(
            client, admin_token, "viewer@example.com", "viewer", "viewer"
        )
        response = client.put(
            f"/users/{viewer_id}",
            json={"username": "updated-viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "updated-viewer"
