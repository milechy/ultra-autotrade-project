# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_smart_wallet_link.py
"""slice4b: POST /auth/wallet/smart-link (Smart Wallet アドレス登録) のテスト。

非カストディアル設計 (案a): JWT 認証ユーザーが自分の SCW を登録。署名検証なし、
unique 制約 + 冪等。設計: docs/privy-aa-paymaster-design.md §6.2 スライス4b。
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-scwlink")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "scwlink_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

SCW = "0x" + "ab" * 20
SCW_MIXED = "0x" + "Ab" * 20  # 同一アドレスの大小混在表記
SCW2 = "0x" + "cd" * 20
BAD_HEX = "0x" + "zz" * 20  # 42 文字だが非 hex


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

    yield override_get_db
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = test_db
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "scwlink_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


def create_viewer_and_login(client: TestClient, admin_token: str, email: str) -> str:
    client.post(
        "/users",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "viewerpass123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "viewerpass123"})
    return r.json()["access_token"]


def _post(client: TestClient, token: str | None, addr: str):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/auth/wallet/smart-link", json={"smart_wallet_address": addr}, headers=headers
    )


def test_register_success_lowercased(client: TestClient) -> None:
    token = get_admin_token(client)
    r = _post(client, token, SCW)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["smart_wallet_address"] == SCW.lower()


def test_idempotent_same_address(client: TestClient) -> None:
    token = get_admin_token(client)
    assert _post(client, token, SCW).status_code == 200
    # 同一アドレス再登録 → no-op 200
    r2 = _post(client, token, SCW)
    assert r2.status_code == 200, r2.text


def test_case_insensitive_idempotent(client: TestClient) -> None:
    token = get_admin_token(client)
    assert _post(client, token, SCW).status_code == 200
    # 大小混在の同一アドレス → no-op 200
    r2 = _post(client, token, SCW_MIXED)
    assert r2.status_code == 200, r2.text


def test_conflict_409_other_user(client: TestClient) -> None:
    admin = get_admin_token(client)
    assert _post(client, admin, SCW).status_code == 200
    viewer = create_viewer_and_login(client, admin, "scw_viewer@example.com")
    r = _post(client, viewer, SCW)
    assert r.status_code == 409, r.text


def test_invalid_hex_format_422(client: TestClient) -> None:
    token = get_admin_token(client)
    r = _post(client, token, BAD_HEX)
    assert r.status_code == 422, r.text


def test_too_short_422(client: TestClient) -> None:
    token = get_admin_token(client)
    r = _post(client, token, "0x123")  # min_length=42 → Pydantic 422
    assert r.status_code == 422, r.text


def test_unauthenticated_401(client: TestClient) -> None:
    r = _post(client, None, SCW)
    assert r.status_code in (401, 403), r.text


def test_viewer_can_register_own(client: TestClient) -> None:
    """VIEWER (消費者) も自分の SCW を登録できる。"""
    admin = get_admin_token(client)
    viewer = create_viewer_and_login(client, admin, "scw_viewer2@example.com")
    r = _post(client, viewer, SCW2)
    assert r.status_code == 200, r.text
    assert r.json()["smart_wallet_address"] == SCW2.lower()
