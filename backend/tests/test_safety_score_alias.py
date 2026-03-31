# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_safety_score_alias.py
"""GET /api/safety-score エンドポイントのテスト。

alias_router は main.py で prefix なしで登録されており、
エンドポイント定義に /api/safety-score を直接記載するため実際のパスは /api/safety-score になる。
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.dependencies import require_viewer
from app.auth.models import UserRole
from app.main import create_app

# エンドポイントの実際のパス
_SAFETY_SCORE_PATH = "/api/safety-score"


def _make_viewer_user() -> MagicMock:
    """テスト用 viewer ユーザーを返す。"""
    user = MagicMock()
    user.id = 2
    user.email = "viewer@example.com"
    user.username = "viewer"
    user.role = UserRole.VIEWER.value
    user.is_active = True
    return user


class TestSafetyScoreAlias:
    """GET /api/safety-score テストクラス。"""

    def _make_client(self) -> TestClient:
        """テスト用 TestClient を作成して返す。"""
        app = create_app()
        app.dependency_overrides[require_viewer] = lambda: _make_viewer_user()
        return TestClient(app)

    def test_get_safety_score_success(self) -> None:
        """正常レスポンスを確認する。"""
        client = self._make_client()
        response = client.get(_SAFETY_SCORE_PATH)

        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert "label" in data
        assert "color" in data
        assert "breakdown" in data

    def test_get_safety_score_breakdown_fields(self) -> None:
        """breakdown に必要なフィールドが含まれること。"""
        client = self._make_client()
        response = client.get(_SAFETY_SCORE_PATH)

        assert response.status_code == 200
        breakdown = response.json()["breakdown"]
        assert "util_score" in breakdown
        assert "hf_score" in breakdown
        assert "vol_score" in breakdown

    def test_get_safety_score_score_is_numeric(self) -> None:
        """score が数値文字列であること（Decimal→str シリアライズ）。"""
        client = self._make_client()
        response = client.get(_SAFETY_SCORE_PATH)

        assert response.status_code == 200
        score_str = response.json()["score"]
        # Decimal は str でシリアライズされる
        float(score_str)  # 数値変換できることを確認
