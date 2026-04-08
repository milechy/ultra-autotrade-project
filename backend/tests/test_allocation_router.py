# backend/tests/test_allocation_router.py
"""
資金割り振り API ルーターの統合テスト。

正常系 CRUD + 異常系（403, 404, 422）+ ロールベースアクセス制御。
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


def _create_alloc(
    client: TestClient, token: str, tester: str = "Alice", amount: str = "1000"
) -> dict:
    r = client.post(
        "/api/partner/allocations",
        json={"tester_name": tester, "allocated_amount_usd": amount},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


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
# CRUD 正常系
# ---------------------------------------------------------------------------


class TestListAllocations:
    def test_empty_list(self, client: TestClient, setup_users: dict) -> None:
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["partner"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_created_allocation(self, client: TestClient, setup_users: dict) -> None:
        _create_alloc(client, setup_users["partner"])
        r = client.get("/api/partner/allocations", headers=_auth(setup_users["partner"]))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["tester_name"] == "Alice"
        assert data[0]["status"] == "active"

    def test_status_filter_withdrawn(self, client: TestClient, setup_users: dict) -> None:
        alloc = _create_alloc(client, setup_users["partner"])
        # withdrawn に更新
        client.put(
            f"/api/partner/allocations/{alloc['id']}",
            json={"status": "withdrawn"},
            headers=_auth(setup_users["partner"]),
        )
        # active フィルタでは空
        r_active = client.get(
            "/api/partner/allocations?status=active", headers=_auth(setup_users["partner"])
        )
        assert r_active.json() == []
        # withdrawn フィルタでは 1 件
        r_withdrawn = client.get(
            "/api/partner/allocations?status=withdrawn", headers=_auth(setup_users["partner"])
        )
        assert len(r_withdrawn.json()) == 1


class TestCreateAllocation:
    def test_create_success(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Bob", "allocated_amount_usd": "2500.50", "notes": "batch-1"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["tester_name"] == "Bob"
        assert Decimal(data["allocated_amount_usd"]) == Decimal("2500.50")
        assert data["notes"] == "batch-1"
        assert data["status"] == "active"

    def test_create_negative_amount_422(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Bad", "allocated_amount_usd": "-100"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 422

    def test_create_zero_amount_422(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "Zero", "allocated_amount_usd": "0"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 422

    def test_create_empty_tester_name_422(self, client: TestClient, setup_users: dict) -> None:
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "  ", "allocated_amount_usd": "100"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 422


class TestUpdateAllocation:
    def test_update_success(self, client: TestClient, setup_users: dict) -> None:
        alloc = _create_alloc(client, setup_users["partner"])
        r = client.put(
            f"/api/partner/allocations/{alloc['id']}",
            json={"tester_name": "AliceUpdated", "allocated_amount_usd": "1500"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["tester_name"] == "AliceUpdated"
        assert Decimal(data["allocated_amount_usd"]) == Decimal("1500")

    def test_update_not_found_404(self, client: TestClient, setup_users: dict) -> None:
        r = client.put(
            "/api/partner/allocations/99999",
            json={"tester_name": "Ghost"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 404

    def test_update_another_partners_record_404(
        self, client: TestClient, setup_users: dict
    ) -> None:
        # admin が作成した割り振り（admin は別 partner_id）を partner が更新しようとする
        admin_alloc = _create_alloc(client, setup_users["admin"], tester="AdminTester")
        r = client.put(
            f"/api/partner/allocations/{admin_alloc['id']}",
            json={"tester_name": "Stolen"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 404

    def test_update_invalid_status_422(self, client: TestClient, setup_users: dict) -> None:
        alloc = _create_alloc(client, setup_users["partner"])
        r = client.put(
            f"/api/partner/allocations/{alloc['id']}",
            json={"status": "invalid_status"},
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 422


class TestDeleteAllocation:
    def test_delete_success(self, client: TestClient, setup_users: dict) -> None:
        alloc = _create_alloc(client, setup_users["partner"])
        r = client.delete(
            f"/api/partner/allocations/{alloc['id']}",
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 204
        # 削除後は空
        r_list = client.get("/api/partner/allocations", headers=_auth(setup_users["partner"]))
        assert r_list.json() == []

    def test_delete_not_found_404(self, client: TestClient, setup_users: dict) -> None:
        r = client.delete(
            "/api/partner/allocations/99999",
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 404

    def test_delete_another_partners_record_404(
        self, client: TestClient, setup_users: dict
    ) -> None:
        admin_alloc = _create_alloc(client, setup_users["admin"], tester="AdminTester")
        r = client.delete(
            f"/api/partner/allocations/{admin_alloc['id']}",
            headers=_auth(setup_users["partner"]),
        )
        assert r.status_code == 404


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

    def test_performance_with_allocations(self, client: TestClient, setup_users: dict) -> None:
        _create_alloc(client, setup_users["partner"], tester="Alice", amount="500")
        _create_alloc(client, setup_users["partner"], tester="Bob", amount="500")

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            r = client.get("/api/partner/performance", headers=_auth(setup_users["partner"]))

        assert r.status_code == 200
        data = r.json()
        assert len(data["testers"]) == 2
        assert Decimal(data["total_supply_usd"]) == Decimal("10000")
        assert Decimal(data["health_factor"]) == Decimal("2.5")

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
