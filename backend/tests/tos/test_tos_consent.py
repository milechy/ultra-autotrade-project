# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/tos/test_tos_consent.py
"""ToS active consent API のテスト (MVP-P0-14 / GID 1215082217739006).

検証項目:
- 認証ガード (401)
- fully_read=False / is_demo_ack=False 時 422
- 成功時の tos_consents + user_actions 並行記録
- consent_hash 改ざん検知
- GET /current の有無 (default uncheck → 同意前は has_consent=False)
"""

import os
import tempfile
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tos-tests-12345678")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.auth.models import User, UserRole  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.tos.models import ToSConsent, UserAction  # noqa: E402, F401
from app.tos.service import compute_consent_hash, verify_consent_hash  # noqa: E402


@pytest.fixture()
def db_setup():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine, TestSession

    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client_and_user(db_setup):
    override_get_db, _engine, TestSession = db_setup
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = TestSession()
    user = User(
        email="tos_user@example.com",
        username="tos_user",
        hashed_password="x",
        role=UserRole.VIEWER.value,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token, _ = AuthService.create_access_token(user_id=user.id, email=user.email, role=user.role)
    user_id = user.id
    db.close()
    return client, token, user_id, TestSession


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_consent_requires_auth(client_and_user):
    client, _token, _uid, _S = client_and_user
    res = client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": True, "fully_read": True},
    )
    assert res.status_code == 401


def test_consent_rejects_when_not_fully_read(client_and_user):
    client, token, _uid, _S = client_and_user
    res = client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": True, "fully_read": False},
        headers=_auth(token),
    )
    assert res.status_code == 422
    assert "読了" in res.json()["detail"]


def test_consent_rejects_when_demo_ack_false(client_and_user):
    client, token, _uid, _S = client_and_user
    res = client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": False, "fully_read": True},
        headers=_auth(token),
    )
    assert res.status_code == 422
    assert "デモ運用" in res.json()["detail"]


def test_consent_persists_and_logs_user_action(client_and_user):
    client, token, uid, TestSession = client_and_user
    res = client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": True, "fully_read": True},
        headers={**_auth(token), "User-Agent": "pytest-agent/1.0"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["user_id"] == uid
    assert body["tos_version"] == "1.0"
    assert body["is_demo_ack"] is True
    assert len(body["consent_hash"]) == 64

    db = TestSession()
    try:
        consents = db.query(ToSConsent).filter(ToSConsent.user_id == uid).all()
        assert len(consents) == 1
        assert consents[0].is_demo_ack is True
        assert consents[0].user_agent == "pytest-agent/1.0"
        assert verify_consent_hash(consents[0]) is True

        actions = (
            db.query(UserAction)
            .filter(UserAction.user_id == uid, UserAction.action_type == "tos_consent")
            .all()
        )
        assert len(actions) == 1
        assert "tos_consent" == actions[0].action_type
        assert "1.0" in (actions[0].payload or "")
    finally:
        db.close()


def test_current_consent_empty_before_consent(client_and_user):
    client, token, _uid, _S = client_and_user
    res = client.get("/api/v1/tos/consent/current", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["has_consent"] is False
    assert body["latest"] is None


def test_current_consent_returns_latest_after_consent(client_and_user):
    client, token, _uid, _S = client_and_user
    client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": True, "fully_read": True},
        headers=_auth(token),
    )
    client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.1", "is_demo_ack": True, "fully_read": True},
        headers=_auth(token),
    )
    res = client.get("/api/v1/tos/consent/current", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert body["has_consent"] is True
    assert body["latest"]["tos_version"] == "1.1"


def test_consent_hash_detects_tampering(client_and_user):
    client, token, uid, TestSession = client_and_user
    client.post(
        "/api/v1/tos/consent",
        json={"tos_version": "1.0", "is_demo_ack": True, "fully_read": True},
        headers=_auth(token),
    )

    db = TestSession()
    try:
        consent = db.query(ToSConsent).filter(ToSConsent.user_id == uid).first()
        assert consent is not None
        assert verify_consent_hash(consent) is True

        consent.tos_version = "1.9-tampered"
        db.commit()
        db.refresh(consent)
        assert verify_consent_hash(consent) is False
    finally:
        db.close()


def test_compute_consent_hash_is_deterministic():
    now = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    h1 = compute_consent_hash(
        user_id=1,
        tos_version="1.0",
        consent_at=now,
        ip="1.2.3.4",
        user_agent="ua",
        is_demo_ack=True,
    )
    h2 = compute_consent_hash(
        user_id=1,
        tos_version="1.0",
        consent_at=now,
        ip="1.2.3.4",
        user_agent="ua",
        is_demo_ack=True,
    )
    h3 = compute_consent_hash(
        user_id=1,
        tos_version="1.0",
        consent_at=now,
        ip="1.2.3.4",
        user_agent="ua",
        is_demo_ack=False,
    )
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64
