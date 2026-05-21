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

from app.auth.models import TIER_JP_LABELS, InvestmentTier, User, UserRole
from app.auth.router import router as auth_router
from app.auth.schemas import UserCreateRequest
from app.auth.service import AuthService
from app.database import Base, get_db
from app.partner.allocation_schemas import AllocationCreateRequest, AllocationUpdateRequest
from app.partner.allocation_service import create_allocation, delete_allocation, update_allocation
from app.users.router import router as users_router
from app.users.tier_service import determine_tier, determine_tier_jpy, refresh_partner_tier

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
    """determine_tier の境界値テスト。デフォルト閾値 $20,000。

    F-2 (2026-04-25): 戻り値を v9 GENERAL から v10 LOWER に変更。
    """

    def test_below_threshold(self) -> None:
        assert determine_tier(Decimal("19999.99")) == InvestmentTier.LOWER.value

    def test_at_threshold(self) -> None:
        assert determine_tier(Decimal("20000.00")) == InvestmentTier.UPPER.value

    def test_above_threshold(self) -> None:
        assert determine_tier(Decimal("20000.01")) == InvestmentTier.UPPER.value

    def test_zero(self) -> None:
        assert determine_tier(Decimal("0")) == InvestmentTier.LOWER.value

    def test_custom_threshold_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIER_THRESHOLD_USD", "10000")
        assert determine_tier(Decimal("9999")) == InvestmentTier.LOWER.value
        assert determine_tier(Decimal("10000")) == InvestmentTier.UPPER.value

    def test_invalid_threshold_env_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TIER_THRESHOLD_USD", "not-a-number")
        # フォールバック → デフォルト $20,000
        assert determine_tier(Decimal("19999")) == InvestmentTier.LOWER.value
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
            assert tier == InvestmentTier.LOWER.value
            db.refresh(partner)
            assert partner.tier == InvestmentTier.LOWER.value

    def test_below_threshold_gives_general(self, test_db: tuple) -> None:
        factory, _ = test_db
        with factory() as db:
            partner = _make_partner(db)
            req = AllocationCreateRequest(
                tester_name="tester1", allocated_amount_usd=Decimal("15000")
            )
            create_allocation(db, partner.id, req)
            db.refresh(partner)
            assert partner.tier == InvestmentTier.LOWER.value

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
            assert partner.tier == InvestmentTier.LOWER.value

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
            assert partner.tier == InvestmentTier.LOWER.value

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
            assert partner.tier == InvestmentTier.LOWER.value


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
            assert r.json()["tier"] == InvestmentTier.LOWER.value

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


# ---------------------------------------------------------------------------
# determine_tier_jpy ユニットテスト (v10 3 層、JPY 境界)
# ---------------------------------------------------------------------------


class TestDetermineTierJpy:
    """v10 三層判定の境界値テスト。

    境界:
      LOWER:  deposit_jpy <= 1,000,000
      MIDDLE: 1,000,001 <= deposit_jpy <= 10,000,000
      UPPER:  deposit_jpy >= 10,000,001
    """

    def test_zero(self) -> None:
        assert determine_tier_jpy(Decimal("0")) == InvestmentTier.LOWER

    def test_just_below_lower_boundary(self) -> None:
        assert determine_tier_jpy(Decimal("999999")) == InvestmentTier.LOWER

    def test_at_lower_boundary(self) -> None:
        # 100 万円ジャストは LOWER に含む
        assert determine_tier_jpy(Decimal("1000000")) == InvestmentTier.LOWER

    def test_just_above_lower_boundary(self) -> None:
        # 100 万円 +1 円から MIDDLE
        assert determine_tier_jpy(Decimal("1000001")) == InvestmentTier.MIDDLE

    def test_mid_middle_range(self) -> None:
        assert determine_tier_jpy(Decimal("5000000")) == InvestmentTier.MIDDLE

    def test_just_below_upper_boundary(self) -> None:
        assert determine_tier_jpy(Decimal("9999999")) == InvestmentTier.MIDDLE

    def test_at_upper_boundary(self) -> None:
        # 1000 万円ジャストは MIDDLE に含む
        assert determine_tier_jpy(Decimal("10000000")) == InvestmentTier.MIDDLE

    def test_just_above_upper_boundary(self) -> None:
        # 1000 万円 +1 円から UPPER
        assert determine_tier_jpy(Decimal("10000001")) == InvestmentTier.UPPER

    def test_far_above_upper(self) -> None:
        assert determine_tier_jpy(Decimal("100000000")) == InvestmentTier.UPPER


class TestTierJpLabels:
    """日本語ラベル辞書テスト。"""

    def test_lower_label(self) -> None:
        assert TIER_JP_LABELS[InvestmentTier.LOWER] == "一般"

    def test_middle_label(self) -> None:
        assert TIER_JP_LABELS[InvestmentTier.MIDDLE] == "ミドル"

    def test_upper_label(self) -> None:
        assert TIER_JP_LABELS[InvestmentTier.UPPER] == "アッパー"

    def test_all_enum_values_have_labels(self) -> None:
        for tier in InvestmentTier:
            assert tier in TIER_JP_LABELS, f"Missing JP label for {tier}"
