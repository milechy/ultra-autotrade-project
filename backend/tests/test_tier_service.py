# backend/tests/test_tier_service.py
"""tier判定サービスおよびtier自動更新のユニットテスト。"""

import os
import tempfile
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-tier-service")

from app.auth.models import InvestmentTier, User, UserRole
from app.auth.router import router as auth_router
from app.auth.schemas import UserCreateRequest
from app.auth.service import AuthService
from app.database import Base, get_db
from app.partner.allocation_schemas import AllocationCreateRequest, AllocationUpdateRequest
from app.partner.allocation_service import create_allocation, delete_allocation, update_allocation
from app.users.router import router as users_router
from app.users.tier_service import determine_tier, refresh_partner_tier

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


# ---------------------------------------------------------------------------
# determine_tier ユニットテスト（境界値）
# ---------------------------------------------------------------------------


class TestDetermineTier:
    """determine_tier の境界値テスト。デフォルト閾値 $20,000。"""

    def test_below_threshold(self) -> None:
        assert determine_tier(Decimal("19999.99")) == InvestmentTier.GENERAL.value

    def test_at_threshold(self) -> None:
        assert determine_tier(Decimal("20000.00")) == InvestmentTier.UPPER.value

    def test_above_threshold(self) -> None:
        assert determine_tier(Decimal("20000.01")) == InvestmentTier.UPPER.value

    def test_zero(self) -> None:
        assert determine_tier(Decimal("0")) == InvestmentTier.GENERAL.value

    def test_custom_threshold_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIER_THRESHOLD_USD", "10000")
        assert determine_tier(Decimal("9999")) == InvestmentTier.GENERAL.value
        assert determine_tier(Decimal("10000")) == InvestmentTier.UPPER.value

    def test_invalid_threshold_env_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TIER_THRESHOLD_USD", "not-a-number")
        # フォールバック → デフォルト $20,000
        assert determine_tier(Decimal("19999")) == InvestmentTier.GENERAL.value
        assert determine_tier(Decimal("20000")) == InvestmentTier.UPPER.value


# ---------------------------------------------------------------------------
# refresh_partner_tier + 割り振り連動テスト
# ---------------------------------------------------------------------------


def _make_partner(db: Session) -> User:
    req = UserCreateRequest(
        email="partner-tier@example.com",
        username="partnertier",
        password="password123!",
        role=UserRole.PARTNER,
    )
    return AuthService.create_user(db, req)


class TestRefreshPartnerTier:
    def test_no_allocations_gives_general(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            tier = refresh_partner_tier(db, partner.id)
            assert tier == InvestmentTier.GENERAL.value
            db.refresh(partner)
            assert partner.tier == InvestmentTier.GENERAL.value

    def test_below_threshold_gives_general(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("15000")
            )
            create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.GENERAL.value

    def test_at_threshold_gives_upper(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("20000")
            )
            create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.UPPER.value

    def test_tier_updates_on_allocation_change(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("10000")
            )
            alloc = create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.GENERAL.value

            # 金額を増やして UPPER に
            update_req = AllocationUpdateRequest(allocated_amount_usd=Decimal("25000"))
            update_allocation(db, alloc.id, partner.id, update_req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.UPPER.value

    def test_tier_updates_on_allocation_delete(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("25000")
            )
            alloc = create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.UPPER.value

            delete_allocation(db, alloc.id, partner.id)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.GENERAL.value

    def test_withdrawn_allocation_excluded_from_tier(self, test_db: tuple) -> None:
        """status=withdrawn の割り振りはティア計算に含まれない。"""
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("25000")
            )
            alloc = create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.UPPER.value

            update_req = AllocationUpdateRequest(status="withdrawn")
            update_allocation(db, alloc.id, partner.id, update_req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.GENERAL.value


# ---------------------------------------------------------------------------
# GET /users/{id}/tier API テスト
# ---------------------------------------------------------------------------


def _create_app(factory: SessionFactory) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)

    def override_db() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


class TestTierAPI:
    def test_partner_can_get_own_tier(self, test_db: tuple) -> None:
        factory, _ = test_db
        app = _create_app(factory)
        with factory() as db:
            partner = _make_partner(db)

        with TestClient(app) as client:
            token = _login(client, "partner-tier@example.com", "password123!")
            r = client.get(
                f"/users/{partner.id}/tier",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            assert r.json()["tier"] == InvestmentTier.GENERAL.value

    def test_viewer_cannot_access_tier(self, test_db: tuple) -> None:
        factory, _ = test_db
        app = _create_app(factory)
        with factory() as db:
            partner = _make_partner(db)
            partner_id = partner.id
            viewer_req = UserCreateRequest(
                email="viewer-tier@example.com",
                username="viewertier",
                password="password123!",
                role=UserRole.VIEWER,
            )
            AuthService.create_user(db, viewer_req)

        with TestClient(app) as client:
            token = _login(client, "viewer-tier@example.com", "password123!")
            r = client.get(
                f"/users/{partner_id}/tier",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403

    def test_partner_cannot_access_other_partner_tier(self, test_db: tuple) -> None:
        factory, _ = test_db
        app = _create_app(factory)
        with factory() as db:
            _make_partner(db)
            other_req = UserCreateRequest(
                email="other-partner@example.com",
                username="otherpartner",
                password="password123!",
                role=UserRole.PARTNER,
            )
            other = AuthService.create_user(db, other_req)
            other_id = other.id

        with TestClient(app) as client:
            token = _login(client, "partner-tier@example.com", "password123!")
            r = client.get(
                f"/users/{other_id}/tier",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403

    def test_tier_not_found(self, test_db: tuple) -> None:
        factory, _ = test_db
        app = _create_app(factory)
        with factory() as db:
            _make_partner(db)

        with TestClient(app) as client:
            token = _login(client, "partner-tier@example.com", "password123!")
            r = client.get(
                "/users/99999/tier",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 404
