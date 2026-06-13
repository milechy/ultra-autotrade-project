# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_account_deletion_request.py
"""アカウント削除申請 API (POST /api/user/delete-request) のテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-deletion")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "deletion_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.users.models import (  # noqa: E402
    ACCOUNT_DELETION_STATUS_PENDING,
    AccountDeletionRequest,
)


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


def register_and_login(
    client: TestClient,
    email: str | None = None,
    username: str = "deluser",
    password: str = "userpassword123",
) -> str:
    # /auth/register は request.email == INITIAL_ADMIN_EMAIL を要求するため、
    # 実際の env 値を使う（他テストモジュールが先に値を設定していても合わせる）。
    if email is None:
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "deletion_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


class TestAccountDeletionRequest:
    def test_requires_auth(self, client: TestClient) -> None:
        """未認証では 401。"""
        r = client.post("/api/user/delete-request")
        assert r.status_code == 401

    def test_creates_pending_request(self, client: TestClient) -> None:
        """認証済みで申請すると 200 + status=pending + already_requested=False。"""
        token = register_and_login(client)
        r = client.post(
            "/api/user/delete-request",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == ACCOUNT_DELETION_STATUS_PENDING
        assert body["already_requested"] is False
        assert "requested_at" in body

    def test_idempotent_second_call(self, client: TestClient) -> None:
        """二回目の申請は already_requested=True を返し、行は重複しない。"""
        token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post("/api/user/delete-request", headers=headers)
        second = client.post("/api/user/delete-request", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["already_requested"] is True

    def test_request_persisted(self, client: TestClient, test_db) -> None:
        """申請が account_deletion_requests に1行だけ永続化される。"""
        token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/user/delete-request", headers=headers)
        client.post("/api/user/delete-request", headers=headers)

        _, SessionLocal = test_db
        db = SessionLocal()
        try:
            rows = db.query(AccountDeletionRequest).all()
            assert len(rows) == 1
            assert rows[0].status == ACCOUNT_DELETION_STATUS_PENDING
        finally:
            db.close()
