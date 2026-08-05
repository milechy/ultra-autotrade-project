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

    def test_settings_put_does_not_write_push_subscriptions_key(self):
        """設定 PUT は購読に一切関与しないこと (2026-08-05 テーブル分離後)。

        以前は購読が同じ JSON セルに同居していたため、PUT /settings が
        push_subscriptions を空配列で上書きして購読を黙って消すバグがあった
        (PR3 で「既存値を引き継ぐ」対策を入れていた)。
        購読を専用テーブルへ分離した現在は、設定 JSON に購読の痕跡を書かないことが
        正しい姿。引き継ぎロジックが復活していないことをここで固定する。
        """
        user = _make_user(json.dumps({"line_enabled": True, "push_enabled": True}))
        db = self._make_db(user)
        self._override_deps(user, db)

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
        assert saved["line_enabled"] is False, "意図した変更は反映される"
        assert "push_subscriptions" not in saved, (
            "購読は専用テーブルの責務。設定 JSON に書き戻してはいけない"
        )

    def test_stale_push_subscriptions_key_is_dropped_on_save(self):
        """移行前に書かれた古い push_subscriptions キーは保存時に落ちること。

        マイグレーションは downgrade 安全性のため JSON 側のキーを残す。
        設定を保存した時点でその残骸が消え、二重の真実源にならないことを確認する
        (購読の実体は既にテーブルへ移行済み)。
        """
        legacy = json.dumps(
            {
                "line_enabled": True,
                "push_enabled": True,
                "push_subscriptions": [
                    {"endpoint": "https://push.example.com/legacy", "p256dh": "k", "auth": "a"}
                ],
            }
        )
        user = _make_user(legacy)
        db = self._make_db(user)
        self._override_deps(user, db)

        res = self.client.put(
            "/api/notifications/settings",
            json={"line_enabled": True, "push_enabled": True, "preferences": {}},
        )
        assert res.status_code == 200
        assert "push_subscriptions" not in json.loads(user.notification_settings_json)


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
