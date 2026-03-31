# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_user_mode.py
"""Tests for user_mode / execution_policy settings and LINE notification helpers."""

import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-user-mode")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    yield override_get_db, engine
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
    username: str = "testuser_mode",
    password: str = "userpassword123",
) -> str:
    if email is None:
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Task 1 Tests: user_mode / execution_policy API
# ---------------------------------------------------------------------------


class TestUserModeSettings:
    def test_get_settings_includes_user_mode_and_execution_policy(self, client: TestClient) -> None:
        """GET /api/user/settings returns user_mode and execution_policy fields."""
        token = register_and_login(client)
        r = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "user_mode" in data
        assert "execution_policy" in data
        # defaults
        assert data["user_mode"] == "managed"
        assert data["execution_policy"] == "auto_execute"

    def test_put_user_mode_active_sets_require_approval(self, client: TestClient) -> None:
        """PUT with user_mode='active' auto-sets execution_policy='require_approval'."""
        token = register_and_login(client, username="testuser_active")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_mode"] == "active"
        assert data["execution_policy"] == "require_approval"

    def test_put_user_mode_managed_sets_auto_execute(self, client: TestClient) -> None:
        """PUT with user_mode='managed' auto-sets execution_policy='auto_execute'."""
        token = register_and_login(client, username="testuser_managed")
        # first set to active
        client.put(
            "/api/user/settings",
            json={"user_mode": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # then revert to managed
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "managed"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_mode"] == "managed"
        assert data["execution_policy"] == "auto_execute"

    def test_put_user_mode_pro_sets_proposal_only(self, client: TestClient) -> None:
        """PUT with user_mode='pro' auto-sets execution_policy='proposal_only'."""
        token = register_and_login(client, username="testuser_pro")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "pro"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_mode"] == "pro"
        assert data["execution_policy"] == "proposal_only"

    def test_put_invalid_user_mode_returns_400(self, client: TestClient) -> None:
        """PUT with invalid user_mode returns 400."""
        token = register_and_login(client, username="testuser_invalid")
        r = client.put(
            "/api/user/settings",
            json={"user_mode": "invalid_mode"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Task 5 Tests: LINE notify helper functions
# ---------------------------------------------------------------------------


class TestLINENotifyHelpers:
    """Verify helpers don't raise exceptions (httpx is mocked)."""

    def _mock_line_client_send(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Patch LINENotifyClient.send to avoid real HTTP and severity filtering."""
        mock_send = MagicMock()
        monkeypatch.setattr("app.notifications.line_notifier.LINENotifyClient.send", mock_send)
        return mock_send

    def test_notify_auto_executed_supply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_send = self._mock_line_client_send(monkeypatch)
        from app.notifications import line_notifier

        line_notifier.notify_auto_executed("SUPPLY", "USDC", 100.0, 3.5)
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert msg.title == "自動取引実行"
        assert "供給" in msg.body

    def test_notify_auto_executed_withdraw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_send = self._mock_line_client_send(monkeypatch)
        from app.notifications import line_notifier

        line_notifier.notify_auto_executed("WITHDRAW", "USDC", 200.0, 3.5)
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert "引き出し" in msg.body

    def test_notify_hf_protection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_send = self._mock_line_client_send(monkeypatch)
        from app.notifications import line_notifier

        line_notifier.notify_hf_protection("WETH", 50.0)
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert msg.title == "資産保護実行"

    def test_notify_proposal_created(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_send = self._mock_line_client_send(monkeypatch)
        from app.notifications import line_notifier

        line_notifier.notify_proposal_created("BUY", "USDC", 100.0)
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert msg.title == "新しい取引提案"

    def test_notify_proposal_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_send = self._mock_line_client_send(monkeypatch)
        from app.notifications import line_notifier

        line_notifier.notify_proposal_timeout("BUY", "USDC")
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert msg.title == "提案タイムアウト"

    def test_notify_no_token_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Functions must not raise even when LINE_NOTIFY_TOKEN is missing."""
        monkeypatch.delenv("LINE_NOTIFY_TOKEN", raising=False)
        from app.notifications import line_notifier

        # Should complete without raising (client logs warning but no exception)
        line_notifier.notify_auto_executed("SUPPLY", "USDC", 100.0, 3.0)
        line_notifier.notify_hf_protection("WETH", 50.0)
        line_notifier.notify_proposal_created("BUY", "USDC", 100.0)
        line_notifier.notify_proposal_timeout("BUY", "USDC")
