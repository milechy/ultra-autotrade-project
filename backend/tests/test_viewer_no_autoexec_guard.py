# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_viewer_no_autoexec_guard.py
"""viewer ロール + auto_execute の許可テスト。

旧 P3-2 (GID 1214993061793196) では viewer + auto_execute を拒否していたが、
LIFF 運用モード画面でエンドユーザー（viewer）が自分で「完全おまかせ(managed =
auto_execute)/アクティブ(active)」を切り替えられるようにする方針変更に伴い、
viewer + auto_execute 拒否ガードは撤廃した。

現仕様:
- viewer も user_mode 変更（auto_execute を含む）を本人セルフサービスで実行可能
- viewer/admin/partner いずれの作成も成功
- auto_execute を持つユーザーを viewer に降格しても許可される
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-p3-2-guard")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ADMIN_EMAIL = "admin_p3_2@example.com"
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
    r = client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "admin_p3_2", "password": _ADMIN_PASSWORD},
    )
    assert r.status_code in (200, 201), f"Admin register failed: {r.text}"
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


def _create_user(client: TestClient, admin_token: str, email: str, role: str) -> dict:
    """admin が指定ロールのユーザーを作成し、レスポンス dict を返す。"""
    r = client.post(
        "/users",
        json={
            "email": email,
            "username": email.split("@")[0].replace(".", "_"),
            "password": "password123",
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return r


def _login(client: TestClient, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# API integration tests: ユーザー作成
# ---------------------------------------------------------------------------


class TestCreateUser:
    def test_create_viewer_gets_require_approval_default(self, client: TestClient) -> None:
        """viewer ユーザー作成時、デフォルトで require_approval になること。

        既定値は安全側の require_approval のまま（auto_execute はユーザーが
        運用モード画面で能動的に「完全おまかせ」を選んだ場合のみ）。
        """
        admin_token = _register_admin(client)
        r = _create_user(client, admin_token, "viewer_create@example.com", "viewer")
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["execution_policy"] in ("require_approval", "auto_execute")

    def test_create_admin_succeeds(self, client: TestClient) -> None:
        """admin ユーザー作成は常に成功すること。"""
        admin_token = _register_admin(client)
        r = _create_user(client, admin_token, "admin_create@example.com", "admin")
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"

    def test_create_partner_succeeds(self, client: TestClient) -> None:
        """partner ユーザー作成は成功すること。"""
        admin_token = _register_admin(client)
        r = _create_user(client, admin_token, "partner_create@example.com", "partner")
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# API integration tests: viewer の auto_execute セルフサービス
# ---------------------------------------------------------------------------


class TestViewerAutoExecuteAllowed:
    def test_viewer_can_set_managed_auto_execute(self, client: TestClient) -> None:
        """viewer が運用モードを managed（= auto_execute）に切り替えられること。"""
        admin_token = _register_admin(client)
        r = _create_user(client, admin_token, "viewer_autoexec@example.com", "viewer")
        assert r.status_code in (200, 201)

        token = _login(client, "viewer_autoexec@example.com")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "managed"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user_mode"] == "managed"
        assert data["execution_policy"] == "auto_execute"


# ---------------------------------------------------------------------------
# API integration tests: ユーザーロール更新（降格は auto_execute でも許可）
# ---------------------------------------------------------------------------


class TestUpdateUserRole:
    def test_demote_admin_with_auto_execute_to_viewer_allowed(self, client: TestClient) -> None:
        """auto_execute を持つ admin を viewer に降格しても許可されること（ガード撤廃後）。"""
        admin_token = _register_admin(client)

        r = _create_user(client, admin_token, "admin_to_demote@example.com", "admin")
        assert r.status_code in (200, 201)
        user_id = r.json()["id"]

        target_token = _login(client, "admin_to_demote@example.com")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "managed"},  # managed → auto_execute
            headers={"Authorization": f"Bearer {target_token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "auto_execute"

        # admin → viewer に降格 → 許可される
        r = client.put(
            f"/users/{user_id}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, (
            f"Expected 200 (guard removed), got {r.status_code}: {r.text}"
        )
        assert r.json()["role"] == "viewer"

    def test_demote_admin_with_require_approval_to_viewer_allowed(self, client: TestClient) -> None:
        """require_approval を持つ admin を viewer に降格すると成功すること。"""
        admin_token = _register_admin(client)

        r = _create_user(client, admin_token, "admin_to_demote2@example.com", "admin")
        assert r.status_code in (200, 201)
        user_id = r.json()["id"]

        target_token = _login(client, "admin_to_demote2@example.com")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "active"},  # active → require_approval
            headers={"Authorization": f"Bearer {target_token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "require_approval"

        r = client.put(
            f"/users/{user_id}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, (
            f"Expected 200 (require_approval is safe), got {r.status_code}: {r.text}"
        )
        assert r.json()["role"] == "viewer"

    def test_viewer_stays_viewer_without_role_change_ok(self, client: TestClient) -> None:
        """viewer ユーザーの email 更新など、role 変更なしは正常に通ること。"""
        admin_token = _register_admin(client)

        r = _create_user(client, admin_token, "viewer_noupdate@example.com", "viewer")
        assert r.status_code in (200, 201)
        user_id = r.json()["id"]

        r = client.put(
            f"/users/{user_id}",
            json={"email": "viewer_noupdate_new@example.com"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200

    def test_update_partner_to_viewer_with_auto_execute_allowed(self, client: TestClient) -> None:
        """auto_execute を持つ partner を viewer に降格しても許可されること（ガード撤廃後）。"""
        admin_token = _register_admin(client)

        r = _create_user(client, admin_token, "partner_to_viewer@example.com", "partner")
        assert r.status_code in (200, 201)
        user_id = r.json()["id"]

        target_token = _login(client, "partner_to_viewer@example.com")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "managed"},
            headers={"Authorization": f"Bearer {target_token}"},
        )
        assert r.status_code == 200
        assert r.json()["execution_policy"] == "auto_execute"

        r = client.put(
            f"/users/{user_id}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, (
            f"Expected 200 (guard removed), got {r.status_code}: {r.text}"
        )
        assert r.json()["role"] == "viewer"
