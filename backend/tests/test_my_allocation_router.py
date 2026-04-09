# backend/tests/test_my_allocation_router.py
"""
GET /api/user/my-allocation エンドポイントの統合テスト。

- 正常系: 割り振りなし / あり / Live Aave PnL / Snapshotフォールバック
- 異常系: 未認証
"""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-my-allocation")

from app.aave.client import AccountData  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.partner.allocation_router import router as allocation_router  # noqa: E402
from app.portfolio.models import PortfolioSnapshot  # noqa: E402
from app.users.router import router as users_router  # noqa: E402
from app.users.settings_router import router as user_settings_router  # noqa: E402

_ADMIN_EMAIL = "my-alloc-admin@example.com"
_ADMIN_PASS = "adminpass123!"
_PARTNER_EMAIL = "my-alloc-partner@example.com"
_PARTNER_PASS = "partnerpass123!"
_TESTER_EMAIL = "my-alloc-tester@example.com"
_TESTER_PASS = "testerpass123!"

_DUMMY_ACCOUNT_DATA = AccountData(
    total_collateral_usd=Decimal("1100"),
    total_debt_usd=Decimal("0"),
    available_borrows_usd=Decimal("0"),
    health_factor=Decimal("999"),
)

SessionFactory = sessionmaker[Session]


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(allocation_router, prefix="/api/partner")
    app.include_router(user_settings_router)
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
def tokens(
    client: TestClient,
    test_db: tuple[SessionFactory, object],
) -> dict[str, str]:
    """admin / partner / tester を登録し、各トークンを返す。"""
    # admin 登録
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "my-alloc-admin", "password": _ADMIN_PASS},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS})
    assert r.status_code == 200
    admin_token = r.json()["access_token"]

    # partner 作成（admin 経由）
    r = client.post(
        "/users",
        json={
            "email": _PARTNER_EMAIL,
            "username": "my-alloc-partner",
            "password": _PARTNER_PASS,
            "role": "partner",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    partner_id = r.json()["id"]

    r = client.post("/auth/login", json={"email": _PARTNER_EMAIL, "password": _PARTNER_PASS})
    assert r.status_code == 200
    partner_token = r.json()["access_token"]

    # tester 作成（partner 経由）
    r = client.post(
        "/users",
        json={
            "email": _TESTER_EMAIL,
            "username": "my-alloc-tester",
            "password": _TESTER_PASS,
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {partner_token}"},
    )
    assert r.status_code == 201

    r = client.post("/auth/login", json={"email": _TESTER_EMAIL, "password": _TESTER_PASS})
    assert r.status_code == 200
    tester_token = r.json()["access_token"]

    return {
        "admin": admin_token,
        "partner": partner_token,
        "tester": tester_token,
        "partner_id": str(partner_id),
    }


class TestGetMyAllocation:
    def test_returns_null_when_no_allocation(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        """割り振りがない場合は null を返す（404 ではない）。"""
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_aave:
            mock_aave.return_value.get_account_data.side_effect = Exception("no aave")
            r = client.get(
                "/api/user/my-allocation",
                headers={"Authorization": f"Bearer {tokens['tester']}"},
            )
        assert r.status_code == 200
        assert r.json() is None

    def test_live_aave_pnl(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        """Aave 接続成功時は is_live=True + PnL がリアルタイム計算される。"""
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "my-alloc-tester", "allocated_amount_usd": "1000.00"},
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 201

        mock_client = MagicMock()
        mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA

        with patch("app.partner.allocation_service.get_default_aave_client", return_value=mock_client):
            r = client.get(
                "/api/user/my-allocation",
                headers={"Authorization": f"Bearer {tokens['tester']}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert Decimal(data["allocated_amount_usd"]) == Decimal("1000.00")
        assert Decimal(data["current_value_usd"]) == Decimal("1100.00")
        assert Decimal(data["pnl_usd"]) == Decimal("100.00")
        assert Decimal(data["pnl_percentage"]) == Decimal("10.00")
        assert data["is_live"] is True
        assert data["partner_name"] == "my-alloc-partner"
        assert data["status"] == "active"

    def test_snapshot_fallback_when_aave_fails(
        self,
        client: TestClient,
        tokens: dict[str, str],
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """Aave 接続失敗時は PortfolioSnapshot にフォールバックし is_live=False になる。"""
        session_factory, _ = test_db

        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "my-alloc-tester", "allocated_amount_usd": "1000.00"},
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 201

        partner_id = int(tokens["partner_id"])
        with session_factory() as db:
            snapshot = PortfolioSnapshot(
                user_id=partner_id,
                total_value_usd=Decimal("1050.00"),
                total_supply_usd=Decimal("1050.00"),
                total_borrow_usd=Decimal("0"),
                recorded_at=datetime.now(timezone.utc),
            )
            db.add(snapshot)
            db.commit()

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_aave:
            mock_aave.return_value.get_account_data.side_effect = Exception("connection error")
            r = client.get(
                "/api/user/my-allocation",
                headers={"Authorization": f"Bearer {tokens['tester']}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert Decimal(data["pnl_usd"]) == Decimal("50.00")
        assert Decimal(data["pnl_percentage"]) == Decimal("5.00")
        assert data["is_live"] is False

    def test_no_pnl_when_aave_fails_and_no_snapshot(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        """Aave 失敗 + Snapshot なし → pnl/current_value は null、is_live=False。"""
        r = client.post(
            "/api/partner/allocations",
            json={"tester_name": "my-alloc-tester", "allocated_amount_usd": "1000.00"},
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 201

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_aave:
            mock_aave.return_value.get_account_data.side_effect = Exception("no aave")
            r = client.get(
                "/api/user/my-allocation",
                headers={"Authorization": f"Bearer {tokens['tester']}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert data["pnl_usd"] is None
        assert data["pnl_percentage"] is None
        assert data["current_value_usd"] is None
        assert data["is_live"] is False

    def test_requires_authentication(self, client: TestClient) -> None:
        """未認証では 401 を返す。"""
        r = client.get("/api/user/my-allocation")
        assert r.status_code == 401

    def test_admin_without_allocation_returns_null(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        """割り振りのない admin は null を返す。"""
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_aave:
            mock_aave.return_value.get_account_data.side_effect = Exception("no aave")
            r = client.get(
                "/api/user/my-allocation",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
        assert r.status_code == 200
        assert r.json() is None
