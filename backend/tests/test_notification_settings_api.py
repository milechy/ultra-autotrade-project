# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_notification_settings_api.py
"""GET/PUT /api/notifications/settings エンドポイントのテスト (Lane C2+E)。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.notifications.router import api_router, router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    return app


def _make_user(notification_settings_json: str | None = None) -> MagicMock:
    user = MagicMock()
    user.notification_settings_json = notification_settings_json
    return user


# ---------------------------------------------------------------------------
# GET /notifications/settings
# ---------------------------------------------------------------------------


class TestGetNotificationSettings:
    def setup_method(self):
        self.app = _make_app()
        self.client = TestClient(self.app)

    def _override_user(self, user: MagicMock) -> None:
        from app.auth.dependencies import require_active_user

        self.app.dependency_overrides[require_active_user] = lambda: user

    def test_returns_default_when_no_json(self):
        self._override_user(_make_user(None))
        res = self.client.get("/notifications/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["line_enabled"] is True
        assert data["push_enabled"] is False
        assert data["preferences"]["emergency_stop"] is True

    def test_returns_stored_settings(self):
        stored = {
            "line_enabled": False,
            "push_enabled": True,
            "preferences": {
                "ai_proposal": False,
                "execution_complete": True,
                "health_factor_warning": True,
                "emergency_stop": True,
                "monthly_report": False,
                "system_notice": True,
            },
        }
        self._override_user(_make_user(json.dumps(stored)))
        res = self.client.get("/notifications/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["line_enabled"] is False
        assert data["push_enabled"] is True
        assert data["preferences"]["ai_proposal"] is False

    def test_returns_default_on_corrupt_json(self):
        self._override_user(_make_user("{invalid json}"))
        res = self.client.get("/notifications/settings")
        assert res.status_code == 200
        assert res.json()["line_enabled"] is True


# ---------------------------------------------------------------------------
# PUT /api/notifications/settings
# ---------------------------------------------------------------------------


class TestPutNotificationSettings:
    def setup_method(self):
        self.app = _make_app()
        self.client = TestClient(self.app)

    def _override_deps(self, user: MagicMock, db: MagicMock) -> None:
        from app.auth.dependencies import require_active_user
        from app.database import get_db

        self.app.dependency_overrides[require_active_user] = lambda: user
        self.app.dependency_overrides[get_db] = lambda: db

    def _make_db(self, user: MagicMock) -> MagicMock:
        return MagicMock()

    def test_saves_settings_to_user(self):
        user = _make_user(None)
        db = self._make_db(user)
        self._override_deps(user, db)

        payload: dict[str, Any] = {
            "line_enabled": False,
            "push_enabled": False,
            "preferences": {
                "ai_proposal": True,
                "execution_complete": True,
                "health_factor_warning": True,
                "emergency_stop": True,
                "monthly_report": False,
                "system_notice": True,
            },
        }
        res = self.client.put("/api/notifications/settings", json=payload)
        assert res.status_code == 200
        db.add.assert_called_once_with(user)
        db.commit.assert_called_once()
        assert user.notification_settings_json is not None
        saved = json.loads(user.notification_settings_json)
        assert saved["line_enabled"] is False
        assert saved["preferences"]["monthly_report"] is False

    def test_emergency_stop_forced_true(self):
        """emergency_stop=False を送っても True に強制されること (Security Rule #6)。"""
        user = _make_user(None)
        db = self._make_db(user)
        self._override_deps(user, db)

        payload: dict[str, Any] = {
            "line_enabled": True,
            "push_enabled": False,
            "preferences": {
                "ai_proposal": True,
                "execution_complete": True,
                "health_factor_warning": True,
                "emergency_stop": False,  # ← 無効化しようとしている
                "monthly_report": True,
                "system_notice": True,
            },
        }
        res = self.client.put("/api/notifications/settings", json=payload)
        assert res.status_code == 200
        saved = json.loads(user.notification_settings_json)
        assert saved["preferences"]["emergency_stop"] is True

    def test_missing_preferences_key_filled_with_defaults(self):
        """stored JSON に preferences キーが無くても GET でデフォルト補完されること。"""
        stored = {"line_enabled": False, "push_enabled": False}
        self._override_user(_make_user(json.dumps(stored)))
        res = self.client.get("/notifications/settings")
        assert res.status_code == 200
        data = res.json()
        assert "preferences" in data
        assert data["preferences"]["emergency_stop"] is True
        assert data["preferences"]["ai_proposal"] is True

    def _override_user(self, user: MagicMock) -> None:
        from app.auth.dependencies import require_active_user

        self.app.dependency_overrides[require_active_user] = lambda: user

    def test_invalid_body_returns_422(self):
        user = _make_user(None)
        db = self._make_db(user)
        self._override_deps(user, db)
        res = self.client.put("/api/notifications/settings", json={"line_enabled": "not_a_bool"})
        assert res.status_code == 422
