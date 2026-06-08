# backend/tests/test_partner_ai_activity.py
"""GET /api/partner/ai-activity エンドポイントのテスト。"""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ai-activity")

from app.ai.models import AIDecision
from app.auth.models import User
from app.auth.router import router as auth_router
from app.database import Base, get_db
from app.partner.router import router as partner_router
from app.users.router import router as users_router

_ADMIN_EMAIL = "ai-activity-admin@example.com"
_ADMIN_PASS = "adminpass123!"


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(partner_router)
    return app


SessionFactory = sessionmaker[Session]


@pytest.fixture()
def test_db() -> Generator[tuple[SessionFactory, object], None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory: SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(
    test_db: tuple[SessionFactory, object],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", _ADMIN_EMAIL)
    factory, _ = test_db
    app = _create_test_app()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    with factory() as db:
        from app.auth.service import AuthService
        admin = User(
            username="ai_activity_admin",
            email=_ADMIN_EMAIL,
            hashed_password=AuthService.hash_password(_ADMIN_PASS),
            role="partner",
            is_active=True,
        )
        db.add(admin)
        db.commit()

    return TestClient(app)


def _partner_token(client: TestClient) -> str:
    resp = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _insert_decision(factory: SessionFactory, **kwargs: object) -> None:
    defaults = {
        "action": "HOLD",
        "confidence": 75,
        "reason": "Macro 25% / Indicator 38% / 両方≥70%",
        "primary_provider": "claude",
        "primary_action": "HOLD",
        "primary_confidence": 75,
        "secondary_provider": "gpt",
        "secondary_action": "HOLD",
        "secondary_confidence": 72,
        "agreed": True,
        "query": "test query",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    with factory() as db:
        db.add(AIDecision(**defaults))
        db.commit()


def test_ai_activity_returns_latest(client: TestClient, test_db: tuple[SessionFactory, object]) -> None:
    """最新判定が返ること。"""
    factory, _ = test_db
    _insert_decision(factory, action="BUY", confidence=80, agreed=False)
    _insert_decision(factory, action="HOLD", confidence=70, agreed=True)

    token = _partner_token(client)
    resp = client.get("/api/partner/ai-activity", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "HOLD"
    assert data["confidence"] == 70
    assert data["agreed"] is True
    assert "created_at" in data


def test_ai_activity_404_when_no_decisions(client: TestClient) -> None:
    """判定データが0件のとき 404 が返ること。"""
    token = _partner_token(client)
    resp = client.get("/api/partner/ai-activity", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_ai_activity_requires_auth(client: TestClient) -> None:
    """認証なしは 401。"""
    resp = client.get("/api/partner/ai-activity")
    assert resp.status_code == 401
