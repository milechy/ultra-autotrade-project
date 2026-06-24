# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/fees/test_dividends.py
"""GET /api/user/dividends のテスト。"""

import os
import tempfile
from datetime import date
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-dividends")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.fees.models import FeeTransaction  # noqa: E402
from app.main import create_app  # noqa: E402


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

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


def _insert_fee(
    SessionLocal, user_id: int, month: date, takehome_jpy: str, rate: str | None
) -> None:
    db = SessionLocal()
    try:
        db.add(
            FeeTransaction(
                user_id=user_id,
                calculation_month=month,
                tier="MIDDLE",
                risk_mode="balanced",
                deposit_amount_jpy=Decimal("1000000"),
                user_takehome_jpy=Decimal(takehome_jpy),
                usd_jpy_rate=Decimal(rate) if rate is not None else None,
            )
        )
        db.commit()
    finally:
        db.close()


class TestDividends:
    def test_empty_returns_200(self, client: TestClient) -> None:
        token = _get_admin_token(client)
        r = client.get("/api/user/dividends", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["dividends"] == []
        assert data["total_jpy"] == "0"

    def test_returns_monthly_takehome(self, client: TestClient, test_db) -> None:
        _, SessionLocal = test_db
        token = _get_admin_token(client)  # admin = user_id 1
        _insert_fee(SessionLocal, 1, date(2026, 5, 1), "10000.00", "152.30")
        _insert_fee(SessionLocal, 1, date(2026, 6, 1), "12500.00", None)  # rate NULL → 150 fallback
        r = client.get("/api/user/dividends", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        # 月次降順: 6月が先頭
        assert [d["month"] for d in data["dividends"]] == ["2026-06-01", "2026-05-01"]
        # 6月 (rate NULL → 150): 12500 / 150 = 83.33
        assert data["dividends"][0]["user_takehome_usd"] == "83.33"
        # 合計
        assert data["total_jpy"] == "22500.00"

    def test_user_isolation(self, client: TestClient, test_db) -> None:
        """他ユーザーの fee_transactions は取得されないこと。"""
        _, SessionLocal = test_db
        token = _get_admin_token(client)  # user_id 1
        _insert_fee(SessionLocal, 1, date(2026, 6, 1), "5000.00", "150.00")
        _insert_fee(SessionLocal, 99999, date(2026, 6, 1), "99999.00", "150.00")  # 別ユーザー
        r = client.get("/api/user/dividends", headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        assert len(data["dividends"]) == 1
        assert data["total_jpy"] == "5000.00"

    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/user/dividends")
        assert r.status_code == 401
