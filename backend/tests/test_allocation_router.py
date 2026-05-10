# backend/tests/test_allocation_router.py
"""
資金割り振り API ルーターの統合テスト。

POST/PUT/DELETE は 410 Gone（廃止）。
GET /allocations と GET /performance はロールチェック含め正常動作を確認。
"""

import os
import tempfile
from collections.abc import Generator
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-allocation-router")

from app.aave.client import AccountData  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.partner.allocation_router import router as allocation_router  # noqa: E402
from app.users.router import router as users_router  # noqa: E402

# テスト固有メールアドレス（他テストと衝突しない）
_ADMIN_EMAIL = "alloc-router-admin@example.com"
_ADMIN_PASS = "adminpass123!"
_PARTNER_EMAIL = "alloc-router-partner@example.com"
_PARTNER_PASS = "partnerpass123!"
_VIEWER_EMAIL = "alloc-router-viewer@example.com"
_VIEWER_PASS = "viewerpass123!"

SessionFactory = sessionmaker[Session]

_DUMMY_ACCOUNT_DATA = AccountData(
    total_collateral_usd=Decimal("10000"),
    total_debt_usd=Decimal("3000"),
    available_borrows_usd=Decimal("5000"),
    health_factor=Decimal("2.5"),
)


# ---------------------------------------------------------------------------
# App / DB fixtures
# ---------------------------------------------------------------------------


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(allocation_router, prefix="/api/partner")
    return app


@pytest.fixture()
def test_db() -> Generator[tuple[SessionFactory, object], None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory: SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(
    test_db: tuple[SessionFactory, object],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", _ADMIN_EMAIL)
    session_factory, _ = test_db
    app = _create_test_app()

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def setup_users(
    client: TestClient,
    test_db: tuple[SessionFactory, object],
) -> dict[str, str]:
    """admin / partner / viewer を登録し、各トークンを返す。"""
    session_factory, _ = test_db

    # admin 登録
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "alloc-admin", "password": _ADMIN_PASS},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS})
    assert r.status_code == 200
    admin_token = r.json()["access_token"]

    # partner 作成（admin 経由）
    r = client.post(
        "/users",
        json={
            "email": _PARTNER_EMAIL,
            "username": "alloc-partner",
            "password": _PARTNER_PASS,
            "role": "partner",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": _PARTNER_EMAIL, "password": _PARTNER_PASS})
    assert r.status_code == 200
    partner_token = r.json()["access_token"]

    # viewer 作成（admin 経由）
    r = client.post(
        "/users",
        json={
            "email": _VIEWER_EMAIL,
            "username": "alloc-viewer",
            "password": _VIEWER_PASS,
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": _VIEWER_EMAIL, "password": _VIEWER_PASS})
    assert r.status_code == 200
    viewer_token = r.json()["access_token"]

    return {
        "admin": admin_token,
        "partner": partner_token,
        "viewer": viewer_token,
    }


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# ロールアクセス制御テスト
# ---------------------------------------------------------------------------


class TestRoleAccess:
    def test_partner_can_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["partner"]))
        assert r.status_code == 200

    def test_admin_can_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["admin"]))
        assert r.status_code == 200

    def test_viewer_cannot_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["viewer"]))
        assert r.status_code == 403

    def test_unauthenticated_cannot_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations")
        assert r.status_code == 401 or r.status_code == 403

    def test_viewer_cannot_create(self, client: TestClient, setup_users: dict) -> None:
        # require_partner 依存が 403 を返す（410 到達前に弾かれる）
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Alice", "allocated_amount_usd": "1000"},
            headers=_auth(setup_users["viewer"]),
        )
        assert r.status_code == 403

    def test_viewer_cannot_get_performance(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/performance", headers=_auth(setup_users["viewer"]))
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /allocations
# ---------------------------------------------------------------------------


class TestListAllocations:
    def test_empty_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["partner"]))
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# POST/PUT/DELETE → 410 Gone（廃止）
# ---------------------------------------------------------------------------


class TestCreateAllocation:
    def test_partner_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Bob", "allocated_amount_usd": "2500"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 410

    def test_admin_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Alice", "allocated_amount_usd": "1000"},
            headers=_auth(setup_users["admin"]),
        )
        assert r.status_code == 410


class TestUpdateAllocation:
    def test_partner_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.put(
            "/api/partner/allocations/1",
            json={"tester_name": "Updated"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 410

    def test_admin_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.put(
            "/api/partner/allocations/1",
            json={"tester_name": "Updated"},
            headers=_auth(setup_users["admin"]),
        )
        assert r.status_code == 410


class TestDeleteAllocation:
    def test_partner_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.delete(
            "/api/partner/allocations/1",
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 410

    def test_admin_gets_410(self, client: TestClient, setup_users: dict) -> None:
        r = client.delete(
            "/api/partner/allocations/1",
            headers=_auth(setup_users["admin"]),
        )
        assert r.status_code == 410


# ---------------------------------------------------------------------------
# パフォーマンスエンドポイント
# ---------------------------------------------------------------------------


class TestGetPerformance:
    def test_performance_empty(self, client: TestClient, setup_users: dict) -> None:
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            r = client.get("/api/partner/performance", headers=_auth(setup_users["partner"]))

        assert r.status_code == 200
        data = r.json()
        assert data["testers"] == []
        assert Decimal(data["total_allocated_usd"]) == Decimal("0")

    def test_performance_partner_role(self, client: TestClient, setup_users: dict) -> None:
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            r = client.get("/api/partner/performance", headers=_auth(setup_users["partner"]))

        assert r.status_code == 200

    def test_performance_admin_role(self, client: TestClient, setup_users: dict) -> None:
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            r = client.get("/api/partner/performance", headers=_auth(setup_users["admin"]))

        assert r.status_code == 200
