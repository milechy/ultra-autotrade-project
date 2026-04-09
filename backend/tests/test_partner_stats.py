# backend/tests/test_partner_stats.py
"""パートナー統計 API テスト。"""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-partner-stats")

# noqa: E402 — env vars must be set before importing app modules
from app.auth.models import User
from app.auth.router import router as auth_router
from app.database import Base, get_db
from app.partner.router import router as partner_router
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot
from app.users.router import router as users_router

# このテスト専用の管理者メール（他のテストと衝突しない）
_PSTATS_ADMIN_EMAIL = "pstats-admin-unique@example.com"
_ADMIN_PASS = "adminpass123!"


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(partner_router)
    return app


SessionFactory = sessionmaker[Session]


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
    # INITIAL_ADMIN_EMAIL をこのテスト専用の値に固定する
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", _PSTATS_ADMIN_EMAIL)
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


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _register_admin(client: TestClient) -> str:
    """専用メールアドレスでアドミン登録してトークンを返す。"""
    client.post(
        "/auth/register",
        json={"email": _PSTATS_ADMIN_EMAIL, "username": "pstatsadmin", "password": _ADMIN_PASS},
    )
    r = client.post("/auth/login", json={"email": _PSTATS_ADMIN_EMAIL, "password": _ADMIN_PASS})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


def _get_user_id(client: TestClient, token: str) -> int:
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _create_viewer(
    client: TestClient,
    admin_token: str,
    session_factory: SessionFactory,
    partner_id: int,
    email: str,
    username: str,
) -> int:
    """admin 経由でビューアーを作成し、DB に Invitation レコードを挿入して user_id を返す。"""
    r = client.post(
        "/users",
        json={
            "email": email,
            "username": username,
            "password": "userpass123!",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201, r.text
    user_id = int(r.json()["id"])

    # users.invited_by に partner_id を設定して紐づきを記録する
    db = session_factory()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None:
            user.invited_by = partner_id
            db.commit()
    finally:
        db.close()

    return user_id


def _add_snapshot(
    session_factory: SessionFactory,
    user_id: int,
    total_value_usd: Decimal,
    recorded_at: datetime,
) -> None:
    db = session_factory()
    try:
        snap = PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=total_value_usd,
            total_supply_usd=total_value_usd,
            total_borrow_usd=Decimal("0"),
            health_factor=Decimal("2.5"),
            recorded_at=recorded_at,
        )
        db.add(snap)
        db.commit()
    finally:
        db.close()


def _add_history(
    session_factory: SessionFactory,
    user_id: int,
    period_type: str,
    period_start: datetime,
    period_end: datetime,
    open_value: Decimal,
    close_value: Decimal,
    pnl_pct: Decimal,
) -> None:
    pnl = close_value - open_value
    db = session_factory()
    try:
        history = PortfolioHistory(
            user_id=user_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            open_value_usd=open_value,
            close_value_usd=close_value,
            high_value_usd=close_value,
            low_value_usd=open_value,
            pnl_usd=pnl,
            pnl_pct=pnl_pct,
            avg_health_factor=Decimal("2.5"),
            snapshot_count=1,
        )
        db.add(history)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 認可テスト
# ---------------------------------------------------------------------------


class TestRequirePartner:
    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/partner/stats")
        assert r.status_code == 401

    def test_viewer_returns_403(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        _create_viewer(client, admin_token, session_factory, partner_id, "v@test.com", "viewer1")

        r = client.post("/auth/login", json={"email": "v@test.com", "password": "userpass123!"})
        viewer_token = r.json()["access_token"]
        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 403

    def test_admin_can_access_stats(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_admin_can_access_monthly(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get("/api/partner/monthly", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/partner/stats
# ---------------------------------------------------------------------------


class TestPartnerStats:
    def test_empty_when_no_users(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_count"] == 0
        assert Decimal(data["total_aum"]) == Decimal("0")
        assert Decimal(data["yesterday_aum"]) == Decimal("0")
        assert data["month_return_pct"] is None
        assert data["yesterday_return_pct"] is None

    def test_total_aum_aggregates_snapshots(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid1 = _create_viewer(client, admin_token, session_factory, partner_id, "u1@t.com", "user1")
        uid2 = _create_viewer(client, admin_token, session_factory, partner_id, "u2@t.com", "user2")

        now = datetime.now(timezone.utc)
        _add_snapshot(session_factory, uid1, Decimal("1000.00"), now)
        _add_snapshot(session_factory, uid2, Decimal("2500.00"), now)

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_count"] == 2
        assert Decimal(data["total_aum"]) == Decimal("3500.00")

    def test_yesterday_return_pct_calculated(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid = _create_viewer(client, admin_token, session_factory, partner_id, "u3@t.com", "user3")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        _add_history(
            session_factory,
            uid,
            "daily",
            yesterday_start,
            today_start,
            Decimal("1000.00"),
            Decimal("1050.00"),
            Decimal("5.0000"),
        )

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["yesterday_return_pct"] is not None
        assert Decimal(data["yesterday_return_pct"]) == Decimal("5.0000")

    def test_month_return_pct_calculated(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid = _create_viewer(client, admin_token, session_factory, partner_id, "u4@t.com", "user4")

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = month_start + timedelta(days=30)

        _add_history(
            session_factory,
            uid,
            "monthly",
            month_start,
            month_end,
            Decimal("10000.00"),
            Decimal("10300.00"),
            Decimal("3.0000"),
        )

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["month_return_pct"] is not None
        assert Decimal(data["month_return_pct"]) == Decimal("3.0000")

    def test_negative_return_passed_through(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid = _create_viewer(client, admin_token, session_factory, partner_id, "u5@t.com", "user5")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        _add_history(
            session_factory,
            uid,
            "daily",
            yesterday_start,
            today_start,
            Decimal("1000.00"),
            Decimal("968.00"),
            Decimal("-3.2000"),
        )

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        data = r.json()
        assert data["yesterday_return_pct"] is not None
        assert Decimal(data["yesterday_return_pct"]) < Decimal("0")


# ---------------------------------------------------------------------------
# /api/partner/users/{user_id}/stats
# ---------------------------------------------------------------------------


class TestUserStats:
    def test_returns_404_for_non_invited_user(self, client: TestClient) -> None:
        admin_token = _register_admin(client)
        r = client.get(
            "/api/partner/users/9999/stats",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 404

    def test_returns_stats_for_invited_user(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid = _create_viewer(client, admin_token, session_factory, partner_id, "u6@t.com", "user6")

        now = datetime.now(timezone.utc)
        _add_snapshot(session_factory, uid, Decimal("5000.00"), now)

        r = client.get(
            f"/api/partner/users/{uid}/stats",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == uid
        assert Decimal(data["today_amount"]) == Decimal("5000.00")
        assert data["yesterday_return_pct"] is None
        assert data["month_return_pct"] is None

    def test_user_stats_with_history(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid = _create_viewer(client, admin_token, session_factory, partner_id, "u7@t.com", "user7")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        _add_snapshot(session_factory, uid, Decimal("8000.00"), now)
        _add_history(
            session_factory,
            uid,
            "daily",
            yesterday_start,
            today_start,
            Decimal("7500.00"),
            Decimal("8000.00"),
            Decimal("6.6667"),
        )
        _add_history(
            session_factory,
            uid,
            "monthly",
            month_start,
            now,
            Decimal("7000.00"),
            Decimal("8000.00"),
            Decimal("14.2857"),
        )

        r = client.get(
            f"/api/partner/users/{uid}/stats",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert Decimal(data["today_amount"]) == Decimal("8000.00")
        assert data["yesterday_return_pct"] is not None
        assert Decimal(data["yesterday_return_pct"]) == Decimal("6.6667")
        assert data["month_return_pct"] is not None
        assert Decimal(data["month_return_pct"]) == Decimal("14.2857")


# ---------------------------------------------------------------------------
# /api/partner/monthly
# ---------------------------------------------------------------------------


class TestMonthlyStats:
    def test_empty_when_no_users(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get("/api/partner/monthly", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == []

    def test_monthly_aggregation(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)
        uid1 = _create_viewer(
            client, admin_token, session_factory, partner_id, "m1@t.com", "muser1"
        )
        uid2 = _create_viewer(
            client, admin_token, session_factory, partner_id, "m2@t.com", "muser2"
        )

        march_start = datetime(2026, 3, 1, tzinfo=timezone.utc)
        march_end = datetime(2026, 3, 31, tzinfo=timezone.utc)
        april_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        april_end = datetime(2026, 4, 30, tzinfo=timezone.utc)

        _add_history(
            session_factory,
            uid1,
            "monthly",
            march_start,
            march_end,
            Decimal("5000.00"),
            Decimal("5200.00"),
            Decimal("4.0000"),
        )
        _add_history(
            session_factory,
            uid2,
            "monthly",
            march_start,
            march_end,
            Decimal("3000.00"),
            Decimal("3090.00"),
            Decimal("3.0000"),
        )
        _add_history(
            session_factory,
            uid1,
            "monthly",
            april_start,
            april_end,
            Decimal("5200.00"),
            Decimal("5304.00"),
            Decimal("2.0000"),
        )

        r = client.get("/api/partner/monthly", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

        march = next(d for d in data if d["month"] == "2026-03")
        assert march["user_count"] == 2
        assert Decimal(march["start_value"]) == Decimal("8000.00")
        assert Decimal(march["end_value"]) == Decimal("8290.00")
        # (8290 - 8000) / 8000 * 100 = 3.625%
        assert Decimal(march["return_pct"]) == Decimal("3.6250")

        april = next(d for d in data if d["month"] == "2026-04")
        assert april["user_count"] == 1
        assert Decimal(april["start_value"]) == Decimal("5200.00")


# ---------------------------------------------------------------------------
# /api/partner/testers
# ---------------------------------------------------------------------------


class TestGetTesters:
    def test_returns_invited_users(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid = _create_viewer(client, admin_token, session_factory, partner_id, "tester1@x.com", "tester1")

        r = client.get("/api/partner/testers", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert any(t["id"] == uid for t in data)
        assert all("username" in t and "email" in t for t in data)

    def test_excludes_uninvited_users(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)

        # Create a user with no invited_by
        r = client.post(
            "/users",
            json={"email": "stranger@x.com", "username": "stranger", "password": "pass1234!", "role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201

        r = client.get("/api/partner/testers", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert not any(t["username"] == "stranger" for t in data)

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/partner/testers")
        assert r.status_code == 401
