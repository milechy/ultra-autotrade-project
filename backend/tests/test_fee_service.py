# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_fee_service.py
"""tier別手数料率サービスおよびAPIエンドポイントのテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-fee")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "fee_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.users.fee_service import (  # noqa: E402
    get_fee_rate_range,
    get_full_fee_schedule,
)

# ---- fee_service unit tests ----


class TestGetFeeRateRange:
    def test_lower_tier(self) -> None:
        result = get_fee_rate_range("LOWER")
        assert result["tier"] == "LOWER"
        assert result["label"] == "一般"
        assert result["min_rate"] == "0.03"
        assert result["max_rate"] == "0.10"
        assert result["min_rate_pct"] == "3"
        assert result["max_rate_pct"] == "10"

    def test_middle_tier(self) -> None:
        result = get_fee_rate_range("MIDDLE")
        assert result["tier"] == "MIDDLE"
        assert result["label"] == "ミドル"
        assert result["min_rate"] == "0.08"
        assert result["max_rate"] == "0.18"
        assert result["min_rate_pct"] == "8"
        assert result["max_rate_pct"] == "18"

    def test_upper_tier(self) -> None:
        result = get_fee_rate_range("UPPER")
        assert result["tier"] == "UPPER"
        assert result["label"] == "アッパー"
        assert result["min_rate"] == "0.15"
        assert result["max_rate"] == "0.25"
        assert result["min_rate_pct"] == "15"
        assert result["max_rate_pct"] == "25"

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            get_fee_rate_range("PLATINUM")

    def test_general_legacy_tier_raises(self) -> None:
        # F-13: GENERAL は削除済み → ValueError
        with pytest.raises(ValueError, match="Unknown tier"):
            get_fee_rate_range("GENERAL")


class TestGetFullFeeSchedule:
    def test_returns_three_tiers(self) -> None:
        schedule = get_full_fee_schedule()
        assert len(schedule) == 3
        tiers = [item["tier"] for item in schedule]
        assert tiers == ["LOWER", "MIDDLE", "UPPER"]

    def test_order_lower_middle_upper(self) -> None:
        schedule = get_full_fee_schedule()
        assert schedule[0]["tier"] == "LOWER"
        assert schedule[1]["tier"] == "MIDDLE"
        assert schedule[2]["tier"] == "UPPER"


# ---- API endpoint tests ----


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
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_and_login(
    client: TestClient,
    email: str | None = None,
    username: str = "feeadmin",
    password: str = "password123",
) -> str:
    if email is None:
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "fee_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


class TestFeeScheduleEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/users/fee-schedule")
        assert r.status_code == 401

    def test_returns_schedule(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get("/users/fee-schedule", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "schedule" in data
        assert "note" in data
        assert len(data["schedule"]) == 3
        tiers = [s["tier"] for s in data["schedule"]]
        assert "LOWER" in tiers
        assert "MIDDLE" in tiers
        assert "UPPER" in tiers

    def test_schedule_rate_values(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get("/users/fee-schedule", headers={"Authorization": f"Bearer {token}"})
        schedule = {s["tier"]: s for s in r.json()["schedule"]}
        assert schedule["LOWER"]["min_rate"] == "0.03"
        assert schedule["LOWER"]["max_rate"] == "0.10"
        assert schedule["MIDDLE"]["min_rate"] == "0.08"
        assert schedule["MIDDLE"]["max_rate"] == "0.18"
        assert schedule["UPPER"]["min_rate"] == "0.15"
        assert schedule["UPPER"]["max_rate"] == "0.25"


class TestUserFeeInfoEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/users/1/fee-info")
        assert r.status_code == 401

    def test_own_user_fee_info(self, client: TestClient) -> None:
        token = _register_and_login(client)
        # Get own user id first
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        user_id = me.json()["id"]

        r = client.get(
            f"/users/{user_id}/fee-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == user_id
        assert data["tier"] in ("LOWER", "MIDDLE", "UPPER")
        assert "fee_rate_range" in data
        assert "min_rate" in data["fee_rate_range"]
        assert "max_rate" in data["fee_rate_range"]

    def test_not_found(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get(
            "/users/99999/fee-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_default_tier_is_lower(self, client: TestClient) -> None:
        token = _register_and_login(client)
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        user_id = me.json()["id"]

        r = client.get(
            f"/users/{user_id}/fee-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        # F-2 (2026-04-25): 新規ユーザーはデフォルトで LOWER (旧 GENERAL)
        assert r.json()["tier"] == "LOWER"
        assert r.json()["fee_rate_range"]["tier"] == "LOWER"
