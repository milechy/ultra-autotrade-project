# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_fee_service.py
"""tier別手数料率サービスおよびAPIエンドポイントのテスト。

v10 (2026-08-06 Asana 1217210615751197): 手数料率の真実源を DB `fee_configs`
(FeeConfigV10) に一本化。旧ハードコード値 (3〜10%/8〜18%/15〜25%) を返すテストは
撤去し、DB 駆動 + fail-open (fee_configs 未投入時は None / 503) のテストに置き換える。
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-fee")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "fee_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.fees.models import FeeConfigV10  # noqa: E402
from app.main import create_app  # noqa: E402
from app.users.fee_service import (  # noqa: E402
    get_fee_rate_range,
    get_full_fee_schedule,
)
from scripts.seed_fee_config_v10 import build_v10_default_config  # noqa: E402


def _seed_fee_config(db: Session) -> None:
    """v10_default 相当の FeeConfigV10 (tier_fee_rates=[0.30, 0.25, 0.20]) を投入する。"""
    db.add(FeeConfigV10(**build_v10_default_config()))
    db.commit()


# ---- fee_service unit tests (DB 駆動) ----


@pytest.fixture()
def fee_db() -> Generator[Session, None, None]:
    """fee_configs テーブルのみを持つ SQLite テスト DB。

    test_seed_fee_config_v10.py の v10_db fixture と同じ最小テーブル構成。
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    FeeConfigV10.__table__.create(bind=engine)  # type: ignore[attr-defined]
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
        FeeConfigV10.__table__.drop(bind=engine)  # type: ignore[attr-defined]
        engine.dispose()
        os.unlink(path)


class TestGetFeeRateRange:
    def test_lower_tier(self, fee_db: Session) -> None:
        _seed_fee_config(fee_db)
        result = get_fee_rate_range("LOWER", fee_db)
        assert result is not None
        assert result["tier"] == "LOWER"
        assert result["label"] == "一般"
        assert result["min_rate"] == result["max_rate"] == "0.3"

    def test_middle_tier(self, fee_db: Session) -> None:
        _seed_fee_config(fee_db)
        result = get_fee_rate_range("MIDDLE", fee_db)
        assert result is not None
        assert result["tier"] == "MIDDLE"
        assert result["label"] == "ミドル"
        assert result["min_rate"] == result["max_rate"] == "0.25"

    def test_upper_tier(self, fee_db: Session) -> None:
        _seed_fee_config(fee_db)
        result = get_fee_rate_range("UPPER", fee_db)
        assert result is not None
        assert result["tier"] == "UPPER"
        assert result["label"] == "アッパー"
        assert result["min_rate"] == result["max_rate"] == "0.2"

    def test_unknown_tier_raises(self, fee_db: Session) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            get_fee_rate_range("PLATINUM", fee_db)

    def test_general_legacy_tier_raises(self, fee_db: Session) -> None:
        # F-13: GENERAL は削除済み → ValueError
        with pytest.raises(ValueError, match="Unknown tier"):
            get_fee_rate_range("GENERAL", fee_db)

    def test_no_active_config_returns_none(self, fee_db: Session) -> None:
        """fee_configs が未投入の場合は fail-open で None を返す (呼び出し元が非表示扱いする)。"""
        assert get_fee_rate_range("LOWER", fee_db) is None


class TestGetFullFeeSchedule:
    def test_returns_three_tiers_in_order(self, fee_db: Session) -> None:
        _seed_fee_config(fee_db)
        schedule = get_full_fee_schedule(fee_db)
        assert schedule is not None
        assert len(schedule) == 3
        assert [item["tier"] for item in schedule] == ["LOWER", "MIDDLE", "UPPER"]

    def test_no_active_config_returns_none(self, fee_db: Session) -> None:
        assert get_full_fee_schedule(fee_db) is None


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


def _seed_fee_config_into_engine(engine) -> None:
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionFactory()
    try:
        _seed_fee_config(db)
    finally:
        db.close()


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

    def test_returns_schedule_when_config_active(self, client: TestClient, test_db) -> None:
        _, engine = test_db
        _seed_fee_config_into_engine(engine)
        token = _register_and_login(client)
        r = client.get("/users/fee-schedule", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "schedule" in data
        assert "note" in data
        tiers = [s["tier"] for s in data["schedule"]]
        assert tiers == ["LOWER", "MIDDLE", "UPPER"]

    def test_schedule_rate_values_match_fee_configs(self, client: TestClient, test_db) -> None:
        _, engine = test_db
        _seed_fee_config_into_engine(engine)
        token = _register_and_login(client)
        r = client.get("/users/fee-schedule", headers={"Authorization": f"Bearer {token}"})
        schedule = {s["tier"]: s for s in r.json()["schedule"]}
        # v10 正本 (build_v10_default_config): tier_fee_rates = [0.30, 0.25, 0.20]
        assert schedule["LOWER"]["min_rate"] == schedule["LOWER"]["max_rate"] == "0.3"
        assert schedule["MIDDLE"]["min_rate"] == schedule["MIDDLE"]["max_rate"] == "0.25"
        assert schedule["UPPER"]["min_rate"] == schedule["UPPER"]["max_rate"] == "0.2"

    def test_returns_503_when_fee_config_not_seeded(self, client: TestClient) -> None:
        """fee_configs 未投入時は 503 (旧ハードコード値へのフォールバック禁止)。"""
        token = _register_and_login(client)
        r = client.get("/users/fee-schedule", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 503


class TestUserFeeInfoEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/users/1/fee-info")
        assert r.status_code == 401

    def test_own_user_fee_info(self, client: TestClient, test_db) -> None:
        _, engine = test_db
        _seed_fee_config_into_engine(engine)
        token = _register_and_login(client)
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

    def test_not_found(self, client: TestClient, test_db) -> None:
        _, engine = test_db
        _seed_fee_config_into_engine(engine)
        token = _register_and_login(client)
        r = client.get(
            "/users/99999/fee-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_default_tier_is_lower(self, client: TestClient, test_db) -> None:
        _, engine = test_db
        _seed_fee_config_into_engine(engine)
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

    def test_returns_503_when_fee_config_not_seeded(self, client: TestClient) -> None:
        """fee_configs 未投入時は 503 (料金プラン非表示)。"""
        token = _register_and_login(client)
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        user_id = me.json()["id"]

        r = client.get(
            f"/users/{user_id}/fee-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 503
