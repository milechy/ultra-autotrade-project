# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/market/test_market_prices.py
"""GET /api/market/prices のテスト。"""

import os
import tempfile
from decimal import Decimal
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-market")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.exchange.router import get_exchange_service  # noqa: E402
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

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db, monkeypatch) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # 外部 USD/JPY API への実ネットワーク呼び出しを抑止 (固定レートを返す)。
    async def _fake_usd_jpy() -> Decimal:
        return Decimal("152.30")

    monkeypatch.setattr("app.market.router._get_usd_jpy", _fake_usd_jpy)
    return TestClient(app)


def _get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


class TestMarketPrices:
    def test_returns_eth_usd_and_usd_jpy(self, client: TestClient) -> None:
        token = _get_admin_token(client)
        r = client.get("/api/market/prices", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        # dummy 取引所は固定 ticker を返すため eth_usd は非 None。
        assert data["eth_usd"] is not None
        assert Decimal(data["eth_usd"]) > Decimal("0")
        assert data["usd_jpy"] == "152.30"
        assert "updated_at" in data

    def test_eth_usd_null_on_exchange_failure(self, client: TestClient) -> None:
        """取引所 ticker 取得がタイムアウト/例外でも eth_usd=null で 200 を返す (fail-open)。"""

        class _FailingClient:
            def fetch_ticker(self, symbol: str) -> dict[str, Any]:
                raise RuntimeError("simulated exchange timeout")

        class _FakeService:
            _client = _FailingClient()

        client.app.dependency_overrides[get_exchange_service] = lambda: _FakeService()
        token = _get_admin_token(client)
        r = client.get("/api/market/prices", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["eth_usd"] is None
        assert data["usd_jpy"] == "152.30"

    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/market/prices")
        assert r.status_code == 401
