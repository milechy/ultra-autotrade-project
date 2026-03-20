"""Tests for terms of service acceptance flow."""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Must be set before app import
os.environ["INITIAL_ADMIN_EMAIL"] = "terms_admin@example.com"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-terms-tests")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

_ADMIN_EMAIL = "terms_admin@example.com"
_ADMIN_PASSWORD = "password123"


@pytest.fixture()
def test_db():
    """Temporary SQLite DB with all tables created."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = Session()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    # Ensure INITIAL_ADMIN_EMAIL is set correctly for this test
    os.environ["INITIAL_ADMIN_EMAIL"] = _ADMIN_EMAIL
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _get_token(client: TestClient) -> str:
    """Register admin user and return access token."""
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "termsadmin", "password": _ADMIN_PASSWORD},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    return r.json()["access_token"]


class TestTermsAcceptance:
    """Test terms acceptance endpoints."""

    def test_terms_status_unauthenticated(self, client: TestClient):
        """Unauthenticated request should return 401."""
        r = client.get("/auth/terms/status")
        assert r.status_code in [401, 403]

    def test_terms_status_not_accepted(self, client: TestClient):
        """New user should need acceptance."""
        token = _get_token(client)
        r = client.get("/auth/terms/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["needs_acceptance"] is True
        assert data["current_version"] == "2.0"
        assert data["accepted"] is False

    def test_accept_terms(self, client: TestClient):
        """User can accept terms."""
        token = _get_token(client)
        r = client.post(
            "/auth/terms/accept",
            json={"version": "2.0"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["accepted"] is True
        assert data["terms_version"] == "2.0"
        assert data["needs_acceptance"] is False
        assert data["terms_accepted_at"] is not None

    def test_terms_status_after_accept(self, client: TestClient):
        """After accepting current version, needs_acceptance should be False."""
        token = _get_token(client)
        h = {"Authorization": f"Bearer {token}"}
        client.post("/auth/terms/accept", json={"version": "2.0"}, headers=h)
        r = client.get("/auth/terms/status", headers=h)
        assert r.status_code == 200
        assert r.json()["needs_acceptance"] is False

    def test_old_version_needs_reaccept(self, client: TestClient):
        """Accepting old version should still require acceptance of current."""
        token = _get_token(client)
        h = {"Authorization": f"Bearer {token}"}
        client.post("/auth/terms/accept", json={"version": "1.0"}, headers=h)
        r = client.get("/auth/terms/status", headers=h)
        assert r.status_code == 200
        assert r.json()["needs_acceptance"] is True

    def test_accept_terms_unauthenticated(self, client: TestClient):
        """Unauthenticated accept should return 401."""
        r = client.post("/auth/terms/accept", json={"version": "2.0"})
        assert r.status_code in [401, 403]

    def test_accept_terms_version_too_long(self, client: TestClient):
        """Version string exceeding max_length should be rejected."""
        token = _get_token(client)
        r = client.post(
            "/auth/terms/accept",
            json={"version": "x" * 21},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422
