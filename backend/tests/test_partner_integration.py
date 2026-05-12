# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_partner_integration.py
"""Lane F-1: /api/partner stats / users / users-{id} 統合テスト。

referrer_id モデル (RAS B) を使用する 3 エンドポイントを検証する。
- wallet_address / tx_hash がレスポンスに含まれないことを schema レベルで保証
- N+1 回避: 複数被紹介者でも正しい集計値が返ること
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-partner-integration")

from app.ai.models import AIDecision  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.partner.router import router as partner_router  # noqa: E402
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot  # noqa: E402
from app.users.router import router as users_router  # noqa: E402

_ADMIN_EMAIL = "pi-admin@example.com"
_ADMIN_PASS = "adminpass123!"

SessionFactory = sessionmaker[Session]


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(partner_router)
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _register_admin(client: TestClient) -> str:
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "piadmin", "password": _ADMIN_PASS},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


def _get_user_id(client: TestClient, token: str) -> int:
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _create_referred_user(
    client: TestClient,
    admin_token: str,
    session_factory: SessionFactory,
    partner_id: int,
    email: str,
    username: str,
    is_active: bool = True,
) -> int:
    """admin 経由でユーザーを作成し referrer_id を設定する。"""
    r = client.post(
        "/users",
        json={"email": email, "username": username, "password": "userpass123!", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201, r.text
    user_id = int(r.json()["id"])

    db = session_factory()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None:
            user.referrer_id = partner_id
            user.is_active = is_active
            db.commit()
    finally:
        db.close()

    return user_id


def _create_user_invited_by_only(
    session_factory: SessionFactory,
    partner_id: int,
    email: str,
    username: str,
) -> int:
    """invited_by のみセット (referrer_id なし) のユーザーを直接 DB に作成。"""
    db = session_factory()
    try:
        user = User(
            email=email,
            username=username,
            hashed_password=AuthService.hash_password("pass123!"),
            role="viewer",
            invited_by=partner_id,
            referrer_id=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _add_snapshot(
    session_factory: SessionFactory,
    user_id: int,
    total_value_usd: Decimal,
) -> None:
    db = session_factory()
    try:
        snap = PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=total_value_usd,
            total_supply_usd=total_value_usd,
            total_borrow_usd=Decimal("0"),
            health_factor=Decimal("2.5"),
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(snap)
        db.commit()
    finally:
        db.close()


def _add_monthly_history(
    session_factory: SessionFactory,
    user_id: int,
    month_start: datetime,
    open_val: Decimal,
    close_val: Decimal,
) -> None:
    pnl = close_val - open_val
    pnl_pct = (
        (pnl / open_val * Decimal("100")).quantize(Decimal("0.0001")) if open_val else Decimal("0")
    )
    db = session_factory()
    try:
        hist = PortfolioHistory(
            user_id=user_id,
            period_type="monthly",
            period_start=month_start,
            period_end=month_start,
            open_value_usd=open_val,
            close_value_usd=close_val,
            high_value_usd=close_val,
            low_value_usd=open_val,
            pnl_usd=pnl,
            pnl_pct=pnl_pct,
            avg_health_factor=Decimal("2.5"),
            snapshot_count=1,
        )
        db.add(hist)
        db.commit()
    finally:
        db.close()


def _add_ai_decision(
    session_factory: SessionFactory,
    user_id: int,
    action: str = "HOLD",
    confidence: int = 70,
) -> None:
    db = session_factory()
    try:
        d = AIDecision(
            user_id=user_id,
            query="market query",
            action=action,
            confidence=confidence,
            primary_provider="claude",
            primary_action=action,
            primary_confidence=confidence,
            agreed=True,
        )
        db.add(d)
        db.commit()
    finally:
        db.close()


# ── tests ─────────────────────────────────────────────────────────────────────


class TestStatsUsesReferrerId:
    def test_referrer_id_user_counted_not_invited_by(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """referrer_id のみのユーザーは集計に含まれ、invited_by のみは含まれない。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        # referrer_id 経由のユーザー
        uid = _create_referred_user(
            client, admin_token, session_factory, partner_id, "ref@pi.com", "refuser"
        )
        _add_snapshot(session_factory, uid, Decimal("5000.00"))

        # invited_by のみ (referrer_id なし) — カウントされないはず
        _create_user_invited_by_only(session_factory, partner_id, "inv@pi.com", "invuser")

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_count"] == 1
        assert Decimal(data["total_aum"]) == Decimal("5000.00")


class TestStatsNewFields:
    def test_total_pnl_and_active_user_count_present(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """total_pnl と active_user_count が stats レスポンスに含まれる。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid = _create_referred_user(
            client, admin_token, session_factory, partner_id, "s1@pi.com", "suser1"
        )
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _add_monthly_history(session_factory, uid, month_start, Decimal("10000"), Decimal("10500"))

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert "total_pnl" in data
        assert "active_user_count" in data
        assert Decimal(data["total_pnl"]) == Decimal("500")
        assert data["active_user_count"] == 1

    def test_active_user_count_excludes_inactive(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """is_active=False のユーザーは active_user_count に含まれない。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        _create_referred_user(
            client, admin_token, session_factory, partner_id, "a1@pi.com", "auser1", is_active=True
        )
        _create_referred_user(
            client, admin_token, session_factory, partner_id, "a2@pi.com", "auser2", is_active=True
        )
        _create_referred_user(
            client, admin_token, session_factory, partner_id, "a3@pi.com", "auser3", is_active=False
        )

        r = client.get("/api/partner/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_count"] == 3
        assert data["active_user_count"] == 2


class TestUsersListEndpoint:
    def test_no_wallet_or_tx_hash_in_response(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """wallet_address / tx_hash がレスポンスに含まれない (法務制約)。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        _create_referred_user(
            client, admin_token, session_factory, partner_id, "wl1@pi.com", "wluser1"
        )

        r = client.get("/api/partner/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        allowed_keys = {
            "user_id",
            "email_masked",
            "total_aum",
            "month_return_pct",
            "is_active",
            "last_judgment_at",
        }
        assert set(rows[0].keys()) == allowed_keys
        assert "wallet_address" not in rows[0]
        assert "tx_hash" not in rows[0]

    def test_n1_safe_two_users_correct_aggregation(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """2 被紹介者で正しい AUM が返る (N+1 回避の回帰検証)。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid1 = _create_referred_user(
            client, admin_token, session_factory, partner_id, "n1@pi.com", "n1user"
        )
        uid2 = _create_referred_user(
            client, admin_token, session_factory, partner_id, "n2@pi.com", "n2user"
        )
        _add_snapshot(session_factory, uid1, Decimal("3000.00"))
        _add_snapshot(session_factory, uid2, Decimal("7000.00"))

        r = client.get("/api/partner/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        aum_map = {row["user_id"]: Decimal(row["total_aum"]) for row in rows}
        assert aum_map[uid1] == Decimal("3000.00")
        assert aum_map[uid2] == Decimal("7000.00")

    def test_empty_returns_empty_list(
        self,
        client: TestClient,
    ) -> None:
        admin_token = _register_admin(client)
        r = client.get("/api/partner/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert r.json() == []

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/partner/users")
        assert r.status_code == 401


class TestUsersDetailEndpoint:
    def test_no_wallet_or_tx_hash_in_response(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """judgment_summary / monthly_performance に wallet/tx_hash が含まれない。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid = _create_referred_user(
            client, admin_token, session_factory, partner_id, "d1@pi.com", "d1user"
        )
        _add_ai_decision(session_factory, uid, "BUY", 85)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _add_monthly_history(session_factory, uid, month_start, Decimal("5000"), Decimal("5100"))

        r = client.get(
            f"/api/partner/users/{uid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()

        assert "wallet_address" not in data
        assert "tx_hash" not in data

        allowed_detail_keys = {"user_id", "email_masked", "monthly_performance", "judgment_summary"}
        assert set(data.keys()) == allowed_detail_keys

        if data["judgment_summary"]:
            j = data["judgment_summary"][0]
            assert "wallet_address" not in j
            assert "tx_hash" not in j
            assert set(j.keys()) == {"action", "confidence", "created_at"}

        if data["monthly_performance"]:
            m = data["monthly_performance"][0]
            assert "wallet_address" not in m
            assert "tx_hash" not in m

    def test_404_for_non_referred_user(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        """referrer_id が自分でないユーザーへのアクセスは 404。"""
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        # 別 partner の被紹介者を作る
        other_user_id = _create_user_invited_by_only(
            session_factory, partner_id + 9999, "other@pi.com", "otheruser"
        )

        r = client.get(
            f"/api/partner/users/{other_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 404

    def test_judgment_summary_returned(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid = _create_referred_user(
            client, admin_token, session_factory, partner_id, "j1@pi.com", "j1user"
        )
        _add_ai_decision(session_factory, uid, "BUY", 80)
        _add_ai_decision(session_factory, uid, "HOLD", 60)

        r = client.get(
            f"/api/partner/users/{uid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["judgment_summary"]) == 2
        actions = {j["action"] for j in data["judgment_summary"]}
        assert "BUY" in actions
        assert "HOLD" in actions

    def test_monthly_performance_returned(
        self,
        client: TestClient,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        admin_token = _register_admin(client)
        partner_id = _get_user_id(client, admin_token)

        uid = _create_referred_user(
            client, admin_token, session_factory, partner_id, "mp1@pi.com", "mp1user"
        )
        month_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        _add_monthly_history(session_factory, uid, month_start, Decimal("10000"), Decimal("10200"))

        r = client.get(
            f"/api/partner/users/{uid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["monthly_performance"]) == 1
        mp = data["monthly_performance"][0]
        assert mp["month"] == "2026-04"
        assert Decimal(mp["start_value"]) == Decimal("10000")
        assert Decimal(mp["end_value"]) == Decimal("10200")
        assert mp["user_count"] == 1
