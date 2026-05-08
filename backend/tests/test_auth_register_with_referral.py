# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_auth_register_with_referral.py
"""RAS Lane 2.1: POST /auth/register-with-referral エンドポイントのテスト。

Gate B ケース:
  Case 4  : 正常 (consent=true / 有効 code) → 201 + referrer_id セット確認
  Case 4-1: 同一 email 重複 → 409
  Case 4-2: code 形式不正 (7桁 "ABC1234") → 422
  Case 5  : consent=false → 422
  Case 6  : 不正 code (DEADBEEF → DB 未登録) → 404
  Extra   : /auth/register が referral_code を受け付けない (削除確認) → 403
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ras-l2.1")

from app.auth.models import User, UserRole  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402

_ADMIN_EMAIL = "ras-l21-admin@example.com"
_ADMIN_PASS = "adminpass123!"
_VALID_CODE = "PARTNER1"

SessionFactory = sessionmaker[Session]


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _register_admin(client: TestClient) -> str:
    r = client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "rasl21admin", "password": _ADMIN_PASS},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["access_token"])


def _create_partner_with_code(db_factory: SessionFactory, referral_code: str) -> User:
    db = db_factory()
    try:
        user = User(
            email=f"partner-{referral_code.lower()}@example.com",
            username=f"partner{referral_code.lower()}",
            hashed_password=AuthService.hash_password("partnerpass1!"),
            role=UserRole.PARTNER.value,
            referral_code=referral_code,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


# ── Case 4: 正常登録 → 201 + referrer_id / referred_consent_at セット ────────


def test_register_with_referral_success_201(client: TestClient, test_db: SessionFactory) -> None:
    _register_admin(client)
    partner = _create_partner_with_code(test_db, _VALID_CODE)

    r = client.post(
        "/auth/register-with-referral",
        json={
            "email": "case4@example.com",
            "username": "case4user",
            "password": "case4pass1!",
            "referral_code": _VALID_CODE,
            "referred_consent": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "case4@example.com"
    assert body["role"] == UserRole.VIEWER.value
    assert "access_token" in body
    assert body["expires_in"] > 0

    # DB 側確認
    db = test_db()
    try:
        new_user = db.query(User).filter(User.email == "case4@example.com").first()
        assert new_user is not None
        assert new_user.referrer_id == partner.id
        assert new_user.referred_consent_at is not None
        assert new_user.role == UserRole.VIEWER.value
    finally:
        db.close()


# ── Case 4-1: 同一 email 重複 → 409 ──────────────────────────────────────────


def test_register_with_referral_duplicate_email_409(
    client: TestClient, test_db: SessionFactory
) -> None:
    _register_admin(client)
    _create_partner_with_code(test_db, _VALID_CODE)

    # 1回目: 成功
    r1 = client.post(
        "/auth/register-with-referral",
        json={
            "email": "dup@example.com",
            "username": "dupuser1",
            "password": "duppass1!",
            "referral_code": _VALID_CODE,
            "referred_consent": True,
        },
    )
    assert r1.status_code == 201, r1.text

    # 2回目: 同一 email → 409
    r2 = client.post(
        "/auth/register-with-referral",
        json={
            "email": "dup@example.com",
            "username": "dupuser2",
            "password": "duppass2!",
            "referral_code": _VALID_CODE,
            "referred_consent": True,
        },
    )
    assert r2.status_code == 409
    assert "email already registered" in r2.json()["detail"]


# ── Case 4-2: referral_code 形式不正 (7桁) → 422 ──────────────────────────────


def test_register_with_referral_invalid_code_format_422(client: TestClient) -> None:
    _register_admin(client)

    r = client.post(
        "/auth/register-with-referral",
        json={
            "email": "fmt@example.com",
            "username": "fmtuser",
            "password": "fmtpass1!",
            "referral_code": "ABC1234",  # 7桁
            "referred_consent": True,
        },
    )
    assert r.status_code == 422
    assert "invalid referral code format" in r.text


# ── Case 5: referred_consent=false → 422 (DB lookup 後) ──────────────────────


def test_register_with_referral_no_consent_422(client: TestClient, test_db: SessionFactory) -> None:
    _register_admin(client)
    _create_partner_with_code(test_db, _VALID_CODE)

    r = client.post(
        "/auth/register-with-referral",
        json={
            "email": "noconsent@example.com",
            "username": "noconsentuser",
            "password": "noconsentpass1!",
            "referral_code": _VALID_CODE,
            "referred_consent": False,
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "referral consent required"


# ── Case 6: referral_code DB 未登録 → 404 ────────────────────────────────────


def test_register_with_referral_code_not_found_404(client: TestClient) -> None:
    _register_admin(client)

    r = client.post(
        "/auth/register-with-referral",
        json={
            "email": "notfound@example.com",
            "username": "notfounduser",
            "password": "notfoundpass1!",
            "referral_code": "DEADBEEF",
            "referred_consent": True,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "referral code not found"


# ── Extra: 特殊文字を含む referral_code 形式不正 → 422 ────────────────────────


def test_register_with_referral_code_special_chars_422(client: TestClient) -> None:
    _register_admin(client)

    r = client.post(
        "/auth/register-with-referral",
        json={
            "email": "spec@example.com",
            "username": "specuser",
            "password": "specpass1!",
            "referral_code": "AB!@#$%^",  # 8文字だが非英数字
            "referred_consent": True,
        },
    )
    assert r.status_code == 422
    assert "invalid referral code format" in r.text


# ── DoD: /auth/register が referral_code を受け付けない (削除確認) ─────────────


def test_register_endpoint_does_not_accept_referral_code(
    client: TestClient, test_db: SessionFactory
) -> None:
    """referral_code フィールドは RegisterRequest から削除済み。
    /auth/register に referral_code を送っても referral 登録にはならず、
    admin ガードで 403 になることを確認する。
    """
    _register_admin(client)
    _create_partner_with_code(test_db, _VALID_CODE)

    # 非 admin email で referral_code を含めて POST → 403 (referral パスなし)
    r = client.post(
        "/auth/register",
        json={
            "email": "sneaky@example.com",
            "username": "sneakyuser",
            "password": "sneakypass1!",
            "referral_code": _VALID_CODE,
            "referred_consent": True,
        },
    )
    assert r.status_code == 403
