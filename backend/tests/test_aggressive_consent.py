# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_aggressive_consent.py
"""[Phase-D D5b] aggressive ティア リスク開示/同意 基盤のテスト。

- POST /api/user/aggressive-consent が冪等に ack を記録し settings に反映されること。
- PUT /auth/risk-mode の aggressive 同意必須ガード (defense-in-depth)。現状は PHASE_1 gate が
  先に aggressive を弾くため、PHASE_1 を緩和した想定 (D6) を monkeypatch で再現して検証する。
"""

import os
import sys
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET_KEY"] = "test-secret-key-aggressive-consent"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["INITIAL_ADMIN_EMAIL"] = "agg_admin@example.com"

from app.auth.models import AGGRESSIVE_ACK_VERSION, RiskMode  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


def _allow_all_risk_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """PHASE_1 gate に全モードを含める (D6 緩和シミュレーション)。

    ``app.auth`` パッケージが ``from .router import router`` で submodule 名を APIRouter で
    shadow するため、実モジュールは sys.modules 経由で取得して patch する。
    """
    auth_router = sys.modules["app.auth.router"]
    monkeypatch.setattr(auth_router, "PHASE_1_ALLOWED_RISK_MODES", frozenset(RiskMode))


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    os.environ["INITIAL_ADMIN_EMAIL"] = "agg_admin@example.com"
    app = create_app()
    app.dependency_overrides[get_db] = test_db
    return TestClient(app)


def _login(client: TestClient) -> str:
    client.post(
        "/auth/register",
        json={"email": "agg_admin@example.com", "username": "aggadmin", "password": "password123"},
    )
    r = client.post(
        "/auth/login", json={"email": "agg_admin@example.com", "password": "password123"}
    )
    return r.json()["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAggressiveConsentEndpoint:
    def test_records_consent_then_idempotent(self, client: TestClient) -> None:
        token = _login(client)
        r1 = client.post("/api/user/aggressive-consent", headers=_hdr(token))
        assert r1.status_code == 200
        assert r1.json()["already_agreed"] is False
        assert r1.json()["aggressive_ack_at"]

        r2 = client.post("/api/user/aggressive-consent", headers=_hdr(token))
        assert r2.status_code == 200
        assert r2.json()["already_agreed"] is True

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post("/api/user/aggressive-consent").status_code == 401

    def test_settings_reflects_ack(self, client: TestClient) -> None:
        token = _login(client)
        assert (
            client.get("/api/user/settings", headers=_hdr(token)).json()["aggressive_ack_at"]
            is None
        )
        client.post("/api/user/aggressive-consent", headers=_hdr(token))
        assert (
            client.get("/api/user/settings", headers=_hdr(token)).json()["aggressive_ack_at"]
            is not None
        )


class TestRiskModeAggressiveGuard:
    """PHASE_1 を緩和した想定 (D6) で aggressive 同意必須ガードを検証する。"""

    def test_aggressive_blocked_without_consent_412(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _allow_all_risk_modes(monkeypatch)
        token = _login(client)
        r = client.put("/auth/risk-mode", json={"mode": "aggressive"}, headers=_hdr(token))
        assert r.status_code == 412
        assert "同意" in r.json()["detail"]

    def test_aggressive_allowed_after_consent(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _allow_all_risk_modes(monkeypatch)
        token = _login(client)
        client.post("/api/user/aggressive-consent", headers=_hdr(token))
        r = client.put("/auth/risk-mode", json={"mode": "aggressive"}, headers=_hdr(token))
        assert r.status_code == 200
        assert r.json()["mode"] == "aggressive"

    def test_conservative_unaffected_by_guard(self, client: TestClient) -> None:
        """conservative は同意不要で従来どおり 200（ガードは aggressive 限定）。"""
        token = _login(client)
        r = client.put("/auth/risk-mode", json={"mode": "conservative"}, headers=_hdr(token))
        assert r.status_code == 200

    def test_ack_version_constant(self) -> None:
        assert AGGRESSIVE_ACK_VERSION == "agg-v1"
