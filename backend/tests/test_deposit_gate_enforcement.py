# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_deposit_gate_enforcement.py
"""A-4: $200 入金ゲートの実行時 enforcement 統合テスト（抜け道回帰）。

提案生成側 (_resolve_proposal_amount) と resolver 本体は
test_proposal_deposit_gate.py / test_deposit_resolver.py でカバー済み。
本ファイルは残る 2 つの enforcement point を TestClient で検証する:

  1. モード切替ゲート  : PUT /api/user/settings user_mode=managed (AUTO 執行) で
                         残高 < MIN_DEPOSIT_USD なら 422 DEPOSIT_BELOW_MINIMUM。
  2. 提案承認ゲート    : POST /api/proposals/{id}/approve で残高 < MIN なら 422。

境界: $199.99 block / $200.00 pass（MIN_DEPOSIT_USD=$200, `<` 比較）。
fail-open: resolve_user_deposit_usd が None（判定不能）なら正規操作を止めない。

resolver は各エンドポイント内で `from app.users.deposit_resolver import
resolve_user_deposit_usd` と遅延 import されるため、パッチ先は
`app.users.deposit_resolver.resolve_user_deposit_usd`。
"""

import os
import tempfile
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-deposit-gate")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "gate_admin@example.com")

from app.auth.models import User  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

_RESOLVER = "app.users.deposit_resolver.resolve_user_deposit_usd"


@pytest.fixture()
def test_db():  # type: ignore[no-untyped-def]
    fd, path = tempfile.mkstemp(suffix=".gate.db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:  # type: ignore[no-untyped-def]
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


_ADMIN_PASSWORD = "GateTestPass123!"


def _admin_email() -> str:
    """登録は「initial admin (first user) かつ email == 現在の INITIAL_ADMIN_EMAIL」のみ許可。

    他テスト (例: test_api_v1_fees) が INITIAL_ADMIN_EMAIL を os.environ に上書きするため、
    module import 時にキャプチャすると実行順序で register 403→login 401 になる。
    必ず呼び出し時 (runtime) に現在値を読むこと。
    """
    return os.environ.get("INITIAL_ADMIN_EMAIL", "gate_admin@example.com")


def _login(client: TestClient) -> str:
    """INITIAL_ADMIN_EMAIL ユーザー（admin ロール）を登録してトークン取得。"""
    email = _admin_email()
    client.post(
        "/auth/register",
        json={"email": email, "username": "gate_admin", "password": _ADMIN_PASSWORD},
    )
    r = client.post("/auth/login", json={"email": email, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return str(r.json()["access_token"])


def _user_id(engine, email: str) -> int:  # type: ignore[no-untyped-def]
    with sessionmaker(bind=engine)() as s:
        uid = s.scalar(select(User.id).where(User.email == email))
    assert uid is not None
    return uid


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_pending_proposal(client: TestClient, token: str, user_id: int) -> int:
    resp = client.post(
        "/api/proposals",
        headers=_auth(token),
        json={
            "user_id": user_id,
            "operation": "SUPPLY",
            "asset": "USDC",
            "amount": "100.000000",
            "amount_usd": "100.00",
            "reason": "A-4 deposit-gate test proposal",
            "expected_hf_after": "2.5",
            "estimated_gas_usd": "0.5",
        },
    )
    assert resp.status_code in (200, 201), f"create proposal failed: {resp.status_code} {resp.text}"
    return int(resp.json()["id"])


# ---------------------------------------------------------------------------
# 1. モード切替ゲート (PUT /api/user/settings user_mode=managed)
# ---------------------------------------------------------------------------


class TestModeSwitchDepositGate:
    def test_managed_below_min_blocked(self, client: TestClient) -> None:
        """残高 $150 (<$200) で managed 切替は 422 DEPOSIT_BELOW_MINIMUM。"""
        token = _login(client)
        with patch(_RESOLVER, return_value=Decimal("150")):
            r = client.put(
                "/api/user/settings", json={"user_mode": "managed"}, headers=_auth(token)
            )
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "DEPOSIT_BELOW_MINIMUM"

    def test_managed_boundary_19999_blocked(self, client: TestClient) -> None:
        """境界: $199.99 は block（`<` 比較で MIN=200 未満）。"""
        token = _login(client)
        with patch(_RESOLVER, return_value=Decimal("199.99")):
            r = client.put(
                "/api/user/settings", json={"user_mode": "managed"}, headers=_auth(token)
            )
        assert r.status_code == 422, r.text

    def test_managed_boundary_200_allowed(self, client: TestClient) -> None:
        """境界: ちょうど $200.00 は pass（200 < 200 は False）。"""
        token = _login(client)
        with patch(_RESOLVER, return_value=Decimal("200.00")):
            r = client.put(
                "/api/user/settings", json={"user_mode": "managed"}, headers=_auth(token)
            )
        assert r.status_code == 200, r.text
        assert r.json()["user_mode"] == "managed"

    def test_managed_unresolvable_fail_open(self, client: TestClient) -> None:
        """判定不能 (None) は fail-open: managed 切替を止めない。"""
        token = _login(client)
        with patch(_RESOLVER, return_value=None):
            r = client.put(
                "/api/user/settings", json={"user_mode": "managed"}, headers=_auth(token)
            )
        assert r.status_code == 200, r.text
        assert r.json()["user_mode"] == "managed"

    def test_active_not_gated_even_below_min(self, client: TestClient) -> None:
        """active (per-trade 承認) は残高 $150 でも切替可能（ゲート対象外）。"""
        token = _login(client)
        with patch(_RESOLVER, return_value=Decimal("150")):
            r = client.put("/api/user/settings", json={"user_mode": "active"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["user_mode"] == "active"


# ---------------------------------------------------------------------------
# 2. 提案承認ゲート (POST /api/proposals/{id}/approve)
# ---------------------------------------------------------------------------


class TestApprovalDepositGate:
    def test_approve_below_min_blocked(self, client: TestClient, test_db) -> None:  # type: ignore[no-untyped-def]
        """残高 $150 (<$200) で承認は 422 DEPOSIT_BELOW_MINIMUM（執行前に遮断）。"""
        _, engine = test_db
        token = _login(client)
        uid = _user_id(engine, _admin_email())
        pid = _create_pending_proposal(client, token, uid)
        with patch(_RESOLVER, return_value=Decimal("150")):
            r = client.post(f"/api/proposals/{pid}/approve", headers=_auth(token))
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "DEPOSIT_BELOW_MINIMUM"

    def test_approve_boundary_19999_blocked(self, client: TestClient, test_db) -> None:  # type: ignore[no-untyped-def]
        """境界: $199.99 は承認 block。"""
        _, engine = test_db
        token = _login(client)
        uid = _user_id(engine, _admin_email())
        pid = _create_pending_proposal(client, token, uid)
        with patch(_RESOLVER, return_value=Decimal("199.99")):
            r = client.post(f"/api/proposals/{pid}/approve", headers=_auth(token))
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "DEPOSIT_BELOW_MINIMUM"
