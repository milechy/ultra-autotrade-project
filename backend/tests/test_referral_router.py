# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_referral_router.py
"""RAS Lane 2: referral ルーターと register 改修の統合テスト。"""

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

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-referral-router")

from app.auth.models import User, UserRole  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.referral.router import router as referral_router  # noqa: E402
from app.transactions.models import Transaction  # noqa: E402

_ADMIN_EMAIL = "ras-l2-admin@example.com"
_ADMIN_PASS = "adminpass123!"


SessionFactory = sessionmaker[Session]


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(referral_router)
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
            "username": "rasl2admin",
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


# ── 1. POST /referral/code (partner JWT) → 200 + 8 桁 ────────────────────────


def test_post_referral_code_partner_returns_200_with_8char(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "partner-a@example.com",
        "partnera",
        "partnerpass1!",
        UserRole.PARTNER.value,
    )
    token = _login(client, "partner-a@example.com", "partnerpass1!")
    r = client.post("/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["referral_code"]) == 8
    assert body["referral_code"].isalnum()
    assert "share_url" in body
    assert body["referral_code"] in body["share_url"]


def test_post_referral_code_returns_same_code_on_repeat(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "partner-b@example.com",
        "partnerb",
        "partnerpass2!",
        UserRole.PARTNER.value,
    )
    token = _login(client, "partner-b@example.com", "partnerpass2!")
    r1 = client.post("/referral/code", headers={"Authorization": f"Bearer {token}"})
    r2 = client.post("/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["referral_code"] == r2.json()["referral_code"]


# ── 2. POST /referral/code (user/admin JWT) → 403 ───────────────────────────


def test_post_referral_code_viewer_returns_403(client: TestClient, test_db: SessionFactory) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "viewer-a@example.com",
        "viewera",
        "viewerpass1!",
        UserRole.VIEWER.value,
    )
    token = _login(client, "viewer-a@example.com", "viewerpass1!")
    r = client.post("/referral/code", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_post_referral_code_admin_returns_403(client: TestClient) -> None:
    """admin は紹介プログラム対象外なので 403 (partner-only)。"""
    admin_token = _register_initial_admin(client)
    r = client.post("/referral/code", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 403


def test_post_referral_code_unauthenticated_returns_401(client: TestClient) -> None:
    r = client.post("/referral/code")
    assert r.status_code == 401


# ── 3. GET /referral/list → 200 + [] ───────────────────────────────────────


def test_get_referral_list_empty(client: TestClient, test_db: SessionFactory) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "partner-c@example.com",
        "partnerc",
        "partnerpass3!",
        UserRole.PARTNER.value,
    )
    token = _login(client, "partner-c@example.com", "partnerpass3!")
    r = client.get("/referral/list", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


def test_get_referral_list_returns_referred_users_with_masked_email(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    partner = _create_user_with_role(
        test_db,
        "partner-d@example.com",
        "partnerd",
        "partnerpass4!",
        UserRole.PARTNER.value,
        referral_code="PARTNERD",
    )

    # 配下ユーザーを 1 人作る (referrer_id=partner.id)
    db = test_db()
    try:
        viewer = User(
            email="yamada@example.com",
            username="yamada1",
            hashed_password=AuthService.hash_password("yamadapass!"),
            role=UserRole.VIEWER.value,
            referrer_id=partner.id,
            referred_consent_at=datetime.now(timezone.utc),
        )
        db.add(viewer)
        db.commit()
    finally:
        db.close()

    token = _login(client, "partner-d@example.com", "partnerpass4!")
    r = client.get("/referral/list", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["email_masked"] == "y***@example.com"
    assert rows[0]["role"] == UserRole.VIEWER.value
    # email 平文がレスポンスに漏れていない
    assert "email" not in rows[0]


# ── 4. POST /auth/register (referral_code + consent=true) → 201 + referrer_id ─


def test_register_with_referral_code_sets_referrer_and_consent(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    partner = _create_user_with_role(
        test_db,
        "partner-e@example.com",
        "partnere",
        "partnerpass5!",
        UserRole.PARTNER.value,
        referral_code="PARTNERE",
    )

    r = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "newuserpass1!",
            "referral_code": "PARTNERE",
            "referred_consent": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "newuser@example.com"
    assert body["role"] == UserRole.VIEWER.value

    # DB 側で referrer_id / referred_consent_at が記録されている
    db = test_db()
    try:
        new_user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert new_user is not None
        assert new_user.referrer_id == partner.id
        assert new_user.referred_consent_at is not None
    finally:
        db.close()


# ── 5. POST /auth/register (consent=false) → 422 ────────────────────────────


def test_register_without_consent_returns_422(client: TestClient, test_db: SessionFactory) -> None:
    _register_initial_admin(client)
    _create_user_with_role(
        test_db,
        "partner-f@example.com",
        "partnerf",
        "partnerpass6!",
        UserRole.PARTNER.value,
        referral_code="PARTNERF",
    )

    r = client.post(
        "/auth/register",
        json={
            "email": "noconsent@example.com",
            "username": "noconsent",
            "password": "noconsentpass1!",
            "referral_code": "PARTNERF",
            "referred_consent": False,
        },
    )
    assert r.status_code == 422
    assert "紹介プログラム同意" in r.json()["detail"]


# ── 6. POST /auth/register (referral_code='DEADBEEF') → 404 ─────────────────


def test_register_with_invalid_referral_code_returns_404(client: TestClient) -> None:
    _register_initial_admin(client)
    r = client.post(
        "/auth/register",
        json={
            "email": "deadbeef@example.com",
            "username": "deadbeef",
            "password": "deadbeefpass1!",
            "referral_code": "DEADBEEF",
            "referred_consent": True,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "無効な紹介コード"


# ── 7. GET /referral/users/{id}/transactions → wallet/tx_hash 含まない ──────


def test_transactions_endpoint_excludes_wallet_and_tx_hash(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    partner = _create_user_with_role(
        test_db,
        "partner-g@example.com",
        "partnerg",
        "partnerpass7!",
        UserRole.PARTNER.value,
        referral_code="PARTNERG",
    )

    # 配下ユーザー + 取引データを作成
    db = test_db()
    try:
        viewer = User(
            email="referred@example.com",
            username="referred1",
            hashed_password=AuthService.hash_password("referredpass!"),
            role=UserRole.VIEWER.value,
            referrer_id=partner.id,
            referred_consent_at=datetime.now(timezone.utc),
        )
        db.add(viewer)
        db.commit()
        db.refresh(viewer)

        # 含まれるべき取引 (deposit / withdraw / borrow / repay)
        for op in ("deposit", "withdraw", "borrow", "repay"):
            tx = Transaction(
                user_id=viewer.id,
                wallet_address="0xabc123abc123abc123abc123abc123abc123",
                operation=op,
                asset="USDC",
                amount=Decimal("100.50"),
                amount_usd=Decimal("100.50"),
                tx_hash="0xdeadbeef" + op,
                chain="base",
                status="confirmed",
            )
            db.add(tx)
        # 含まれないべき取引 (rebalance)
        rebalance_tx = Transaction(
            user_id=viewer.id,
            wallet_address="0xdef",
            operation="rebalance",
            asset="USDC",
            amount=Decimal("999.00"),
            amount_usd=Decimal("999.00"),
            tx_hash="0xignoreme",
            chain="base",
            status="confirmed",
        )
        db.add(rebalance_tx)
        db.commit()
        viewer_id = viewer.id
    finally:
        db.close()

    token = _login(client, "partner-g@example.com", "partnerpass7!")
    r = client.get(
        f"/referral/users/{viewer_id}/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 4
    types = {row["type"] for row in rows}
    assert types == {"deposit", "withdraw", "borrow", "repay"}

    for row in rows:
        # 法務未クリア項目がレスポンスに含まれていない
        assert "wallet_address" not in row
        assert "tx_hash" not in row
        assert set(row.keys()) == {"type", "amount", "occurred_at"}
        # amount は文字列で返却される (Decimal の文字列化)
        assert isinstance(row["amount"], str)


def test_transactions_endpoint_403_for_other_partners_referred_user(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_initial_admin(client)
    partner_a = _create_user_with_role(
        test_db,
        "partner-h@example.com",
        "partnerh",
        "partnerpass8!",
        UserRole.PARTNER.value,
        referral_code="PARTNERH",
    )
    _create_user_with_role(
        test_db,
        "partner-i@example.com",
        "partneri",
        "partnerpass9!",
        UserRole.PARTNER.value,
        referral_code="PARTNERI",
    )

    # partner_a 配下のユーザー
    db = test_db()
    try:
        viewer = User(
            email="under-a@example.com",
            username="undera",
            hashed_password=AuthService.hash_password("xpass!"),
            role=UserRole.VIEWER.value,
            referrer_id=partner_a.id,
        )
        db.add(viewer)
        db.commit()
        db.refresh(viewer)
        viewer_id = viewer.id
    finally:
        db.close()

    # partner_i (別 partner) のトークンで取得しようとする → 403
    token_i = _login(client, "partner-i@example.com", "partnerpass9!")
    r = client.get(
        f"/referral/users/{viewer_id}/transactions",
        headers={"Authorization": f"Bearer {token_i}"},
    )
    assert r.status_code == 403
