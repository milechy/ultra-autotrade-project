# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_api_referral_router.py
"""Lane C1: /api/referral/* エンドポイントの統合テスト。"""

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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-api-referral")

from app.auth.models import User, UserRole  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.referral.api_router import router as referral_api_router  # noqa: E402
from app.transactions.models import Transaction  # noqa: E402

_ADMIN_EMAIL = "api-ref-admin@example.com"
_ADMIN_PASS = "adminpass123!"

SessionFactory = sessionmaker[Session]


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(referral_api_router)
    return app


@pytest.fixture()
def test_db() -> Generator[SessionFactory, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory: SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(
    test_db: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", _ADMIN_EMAIL)
    app = _create_test_app()

    def override_get_db() -> Generator[Session, None, None]:
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


# ── ヘルパー ─────────────────────────────────────────────────────────────────


def _register_initial_admin(client: TestClient) -> str:
    r = client.post(
        "/auth/register",
        json={
            "email": _ADMIN_EMAIL,
            "username": "apirefadmin",
            "password": _ADMIN_PASS,
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["access_token"])


def _create_user_with_role(
    db_factory: SessionFactory,
    email: str,
    username: str,
    password: str,
    role: str,
    referral_code: str | None = None,
) -> User:
    db = db_factory()
    try:
        user = User(
            email=email,
            username=username,
            hashed_password=AuthService.hash_password(password),
            role=role,
            referral_code=referral_code,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


# ── POST /api/referral/code ──────────────────────────────────────────────────


def test_post_api_referral_code_viewer_returns_200(
    client: TestClient, test_db: SessionFactory
) -> None:
    """VIEWER ロールでもコード発行できる (partner-only ではない)。"""
    _register_initial_admin(client)
    _create_user_with_role(
        test_db, "viewer-ref@example.com", "viewerref", "viewerpass1!", UserRole.VIEWER.value
    )
    token = _login(client, "viewer-ref@example.com", "viewerpass1!")
    r = client.post("/api/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["referral_code"]) == 8
    assert body["referral_code"].isalnum()
    assert "share_url" in body
    assert body["referral_code"] in body["share_url"]


def test_post_api_referral_code_partner_returns_200(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db, "partner-ref@example.com", "partnerref", "partnerpass1!", UserRole.PARTNER.value
    )
    token = _login(client, "partner-ref@example.com", "partnerpass1!")
    r = client.post("/api/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_post_api_referral_code_is_idempotent(client: TestClient, test_db: SessionFactory) -> None:
    """同一ユーザーが複数回呼んでも同じコードが返る。"""
    _register_initial_admin(client)
    _create_user_with_role(
        test_db, "viewer-idem@example.com", "vieweridem", "viewerpass2!", UserRole.VIEWER.value
    )
    token = _login(client, "viewer-idem@example.com", "viewerpass2!")
    r1 = client.post("/api/referral/code", headers={"Authorization": f"Bearer {token}"})
    r2 = client.post("/api/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["referral_code"] == r2.json()["referral_code"]


def test_post_api_referral_code_unauthenticated_returns_401(client: TestClient) -> None:
    r = client.post("/api/referral/code")
    assert r.status_code == 401


# ── GET /api/referral/earnings ───────────────────────────────────────────────


def test_get_api_referral_earnings_empty(client: TestClient, test_db: SessionFactory) -> None:
    """紹介ユーザーなし: referral_count=0、referred_users=[]。"""
    _register_initial_admin(client)
    _create_user_with_role(
        test_db, "viewer-earn@example.com", "viewerearn", "viewerpass3!", UserRole.VIEWER.value
    )
    token = _login(client, "viewer-earn@example.com", "viewerpass3!")
    r = client.get("/api/referral/earnings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["referral_count"] == 0
    assert body["referred_users"] == []
    assert body["referral_code"] == ""
    assert "current_month_reward_jpy" in body
    assert "total_payout_jpy" in body
    assert "campaign_rate" in body


def test_get_api_referral_earnings_returns_code_if_already_issued(
    client: TestClient, test_db: SessionFactory
) -> None:
    """既発行コードがあれば earnings に反映される。"""
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "viewer-hascode@example.com",
        "viewerhascode",
        "viewerpass4!",
        UserRole.VIEWER.value,
        referral_code="MYCODE12",
    )
    token = _login(client, "viewer-hascode@example.com", "viewerpass4!")
    r = client.get("/api/referral/earnings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["referral_code"] == "MYCODE12"


def test_get_api_referral_earnings_with_referred_users(
    client: TestClient, test_db: SessionFactory
) -> None:
    """紹介済みユーザーが referred_users に含まれ status が判定される。"""
    _register_initial_admin(client)
    referrer = _create_user_with_role(
        test_db,
        "referrer@example.com",
        "referreruser",
        "referrerpass1!",
        UserRole.VIEWER.value,
        referral_code="REFER001",
    )

    db = test_db()
    try:
        # 取引なし (登録済み)
        no_tx_user = User(
            email="notx@example.com",
            username="notxuser",
            hashed_password=AuthService.hash_password("notxpass!"),
            role=UserRole.VIEWER.value,
            referrer_id=referrer.id,
            referred_consent_at=datetime.now(timezone.utc),
        )
        db.add(no_tx_user)

        # 取引あり (運用中)
        has_tx_user = User(
            email="hastx@example.com",
            username="hastxuser",
            hashed_password=AuthService.hash_password("hastxpass!"),
            role=UserRole.VIEWER.value,
            referrer_id=referrer.id,
            referred_consent_at=datetime.now(timezone.utc),
        )
        db.add(has_tx_user)
        db.commit()
        db.refresh(has_tx_user)

        tx = Transaction(
            user_id=has_tx_user.id,
            wallet_address="0xabc",
            operation="deposit",
            asset="USDC",
            amount=Decimal("100"),
            amount_usd=Decimal("100"),
            tx_hash="0xhash1",
            chain="base",
            status="confirmed",
        )
        db.add(tx)
        db.commit()
    finally:
        db.close()

    token = _login(client, "referrer@example.com", "referrerpass1!")
    r = client.get("/api/referral/earnings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["referral_count"] == 2
    assert len(body["referred_users"]) == 2

    statuses = {u["name"]: u["status"] for u in body["referred_users"]}
    assert statuses["notxuser"] == "registered"
    assert statuses["hastxuser"] == "active"

    for u in body["referred_users"]:
        assert "joined_at" in u
        assert u["reward_jpy"] == "0"


def test_get_api_referral_earnings_unauthenticated_returns_401(client: TestClient) -> None:
    r = client.get("/api/referral/earnings")
    assert r.status_code == 401
