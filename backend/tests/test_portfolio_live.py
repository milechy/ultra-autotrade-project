# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_portfolio_live.py
"""GET /api/portfolio ライブAaveデータエンドポイントのテスト。"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.auth.dependencies import require_viewer
from app.auth.models import UserRole
from app.main import create_app


def _make_viewer_user() -> MagicMock:
    """テスト用 viewer ユーザーを返す。"""
    user = MagicMock()
    user.id = 2
    user.email = "viewer@example.com"
    user.username = "viewer"
    user.role = UserRole.VIEWER.value
    user.is_active = True
    return user


def _make_dummy_account_data() -> MagicMock:
    """テスト用 AccountData モックを返す。"""
    account_data = MagicMock()
    account_data.total_collateral_usd = Decimal("10000")
    account_data.total_debt_usd = Decimal("3000")
    account_data.available_borrows_usd = Decimal("5000")
    account_data.health_factor = Decimal("2.5")
    return account_data


def _make_inf_account_data() -> MagicMock:
    """health_factor が inf のテスト用 AccountData モックを返す。"""
    account_data = MagicMock()
    account_data.total_collateral_usd = Decimal("0")
    account_data.total_debt_usd = Decimal("0")
    account_data.available_borrows_usd = Decimal("0")
    account_data.health_factor = Decimal("inf")
    return account_data


# ローカルインポートのパッチターゲット（関数内で import するため元モジュールを差し替える）
_PATCH_TARGET = "app.aave.client.get_default_aave_client"


class TestPortfolioLive:
    """GET /api/portfolio テストクラス。"""

    def setup_method(self) -> None:
        """各テスト前にキャッシュをクリアする。"""
        import app.portfolio.router as portfolio_router

        portfolio_router._live_cache.clear()

    def _make_client(self) -> TestClient:
        """テスト用 TestClient を作成して返す。"""
        app = create_app()
        app.dependency_overrides[require_viewer] = lambda: _make_viewer_user()
        return TestClient(app)

    def test_get_live_portfolio_success(self) -> None:
        """正常レスポンスを確認する。"""
        client = self._make_client()
        mock_account_data = _make_dummy_account_data()
        mock_client = MagicMock()
        mock_client.get_account_data.return_value = mock_account_data

        with patch(_PATCH_TARGET, return_value=mock_client):
            response = client.get("/api/portfolio")

        assert response.status_code == 200
        data = response.json()
        assert "total_supply_usd" in data
        assert "total_borrow_usd" in data
        assert "health_factor" in data
        assert "net_worth_usd" in data
        assert "chain" in data
        assert "fetched_at" in data
        assert data["total_supply_usd"] == "10000"
        assert data["total_borrow_usd"] == "3000"
        assert data["health_factor"] == "2.5"
        assert data["net_worth_usd"] == "7000"
        assert data["chain"] == "arbitrum_sepolia"
        assert data["positions"] == []

    def test_get_live_portfolio_health_factor_inf(self) -> None:
        """health_factor が inf の場合に None を返すこと。"""
        client = self._make_client()
        mock_account_data = _make_inf_account_data()
        mock_client = MagicMock()
        mock_client.get_account_data.return_value = mock_account_data

        with patch(_PATCH_TARGET, return_value=mock_client):
            response = client.get("/api/portfolio")

        assert response.status_code == 200
        data = response.json()
        assert data["health_factor"] is None

    def test_get_live_portfolio_cache(self) -> None:
        """2回呼び出してAaveクライアントが1回しか呼ばれないこと（キャッシュ動作確認）。"""
        client = self._make_client()
        mock_account_data = _make_dummy_account_data()
        mock_client = MagicMock()
        mock_client.get_account_data.return_value = mock_account_data

        with patch(_PATCH_TARGET, return_value=mock_client):
            resp1 = client.get("/api/portfolio")
            resp2 = client.get("/api/portfolio")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # キャッシュが効いているため get_account_data は1回だけ呼ばれる
        mock_client.get_account_data.assert_called_once()

    def test_get_live_portfolio_chain_param(self) -> None:
        """chain パラメータが正しくレスポンスに含まれること。"""
        client = self._make_client()
        mock_account_data = _make_dummy_account_data()
        mock_client = MagicMock()
        mock_client.get_account_data.return_value = mock_account_data

        with patch(_PATCH_TARGET, return_value=mock_client):
            response = client.get("/api/portfolio?chain=arbitrum")

        assert response.status_code == 200
        assert response.json()["chain"] == "arbitrum"

    def test_get_live_portfolio_aave_error_returns_500(self) -> None:
        """Aaveクライアントがエラーを投げた場合に500を返すこと。"""
        client = self._make_client()

        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("RPC connection failed"),
        ):
            response = client.get("/api/portfolio")

        assert response.status_code == 500
