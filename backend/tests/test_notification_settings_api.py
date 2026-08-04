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

    def test_generic_settings_put_preserves_push_subscriptions(self):
        """★2026-08-04 PR3 回帰防止: push_subscriptions は /push/subscribe 専用エンドポイント
        経由でのみ変更されるべきで、他の通知設定 (line_enabled 等) を変更するだけの
        汎用 PUT /settings で黙って空配列に上書きされてはならない。
        NotificationSettingsModel が push_subscriptions を含まないため、対策なしでは
        body.model_dump_json() が丸ごと上書きし購読が消える。"""
        existing = json.dumps(
            {
                "line_enabled": True,
                "push_enabled": True,
                "preferences": {},
                "push_subscriptions": [
                    {"endpoint": "https://push.example.com/keep-me", "p256dh": "k", "auth": "a"}
                ],
            }
        )
        user = _make_user(existing)
        db = self._make_db(user)
        self._override_deps(user, db)

        # push_subscriptions を含まない、既存の通知設定変更 (line_enabled のみ変更) を PUT する。
        payload: dict[str, Any] = {
            "line_enabled": False,
            "push_enabled": True,
            "preferences": {
                "ai_proposal": True,
                "execution_complete": True,
                "health_factor_warning": True,
                "emergency_stop": True,
                "monthly_report": True,
                "system_notice": True,
            },
        }
        res = self.client.put("/api/notifications/settings", json=payload)
        assert res.status_code == 200

        saved = json.loads(user.notification_settings_json)
        assert saved["line_enabled"] is False  # 意図した変更は反映される
        assert saved["push_subscriptions"] == [
            {"endpoint": "https://push.example.com/keep-me", "p256dh": "k", "auth": "a"}
        ]  # 購読は消えない

    def test_settings_put_with_no_prior_push_subscriptions_defaults_to_empty(self):
        """push_subscriptions キーが元々存在しない (未購読ユーザー) 場合は空配列で保存される。"""
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
                "emergency_stop": True,
                "monthly_report": True,
                "system_notice": True,
            },
        }
        res = self.client.put("/api/notifications/settings", json=payload)
        assert res.status_code == 200
        saved = json.loads(user.notification_settings_json)
        assert saved["push_subscriptions"] == []


# ---------------------------------------------------------------------------
# POST /api/notifications/push/test (liff-chat「テスト通知」ボタンのパス)
# ---------------------------------------------------------------------------


class TestTestPushAliasPaths:
    """NotificationPanel の「テスト通知」ボタンは body 無しで
    POST /api/notifications/push/test を叩く。frontend と完全一致のパス +
    後方互換 /api/notifications/test-push が body 無しで 200 を返すこと。
    VAPID 未設定 + LINE 未設定の既定環境では送信 0 件・200 を期待。"""

    def setup_method(self):
        self.app = _make_app()
        self.client = TestClient(self.app)
        from app.auth.dependencies import require_active_user

        self.app.dependency_overrides[require_active_user] = lambda: _make_user(None)

    def test_canonical_api_path_no_body_returns_200(self):
        # frontend NotificationPanel.handleTestNotification が叩く正確なパス
        res = self.client.post("/api/notifications/push/test")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"

    def test_legacy_test_push_path_no_body_returns_200(self):
        res = self.client.post("/api/notifications/test-push")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"

    def test_non_api_push_test_path_no_body_returns_200(self):
        res = self.client.post("/notifications/push/test")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"
