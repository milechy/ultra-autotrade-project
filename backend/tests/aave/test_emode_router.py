# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_emode_router.py
"""
GET /aave/emode / POST /aave/emode のルーターテスト。

カバレッジ:
- GET 200 (viewer 以上でアクセス可能)
- POST 401 (viewer では POST 不可)
- POST 200 dry_run=True (admin で dry_run)
- POST 503 wallet 未設定
- POST 409 HF < 1.6 ブロック
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.aave.client import AaveClientBase, AaveClientError, AccountData
from app.auth.models import User

# ── テスト用ダミークライアント ─────────────────────────────────────────────


class _StubAaveClient(AaveClientBase):
    """テスト用スタブクライアント。HF と eMode を制御可能。"""

    def __init__(self, hf: Decimal = Decimal("2.5"), emode_id: int = 0) -> None:
        self._hf = hf
        self._emode_id = emode_id

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self._hf

    def get_account_data(self, wallet_address: str) -> AccountData:
        return AccountData(
            total_collateral_usd=Decimal("10000"),
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=self._hf,
        )

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, Any] | str":
        return {"tx_hash": "0xstub", "amount": str(amount), "dry_run": dry_run}

    def withdraw(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, Any] | str":
        return {"tx_hash": "0xstub", "amount": str(amount), "dry_run": dry_run}

    def get_user_emode(self, wallet_address: str) -> int:
        return self._emode_id

    def build_set_emode_tx(
        self,
        category_id: int,
        wallet_address: str,
        dry_run: bool = False,
    ) -> "dict[str, Any]":
        if dry_run:
            return {"category_id": category_id, "dry_run": True}
        return {
            "set_emode_tx": {
                "to": "0xPOOL",
                "data": "0xstub_data",
                "from": wallet_address,
                "chainId": 42161,
                "value": "0x0",
            }
        }

    def execute_set_emode(
        self,
        category_id: int,
        wallet_address: str,
        private_key: str = "",
    ) -> "dict[str, Any]":
        return {"tx_hash": "0xstub_set_emode_hash", "category_id": category_id}


# ── 認証ユーザースタブ ──────────────────────────────────────────────────────


def _make_admin_user() -> User:
    """テスト用の admin ユーザーオブジェクト。"""
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "admin@test.example"
    user.role = "admin"
    return user


def _make_viewer_user() -> User:
    """テスト用の viewer ユーザーオブジェクト。"""
    user = MagicMock(spec=User)
    user.id = 2
    user.email = "viewer@test.example"
    user.role = "viewer"
    return user


def _raise_403() -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="権限が不足しています")


# ── TestClient fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def admin_client() -> TestClient:
    """admin 権限で認証済みのテストクライアント。"""
    from app.auth.dependencies import require_admin, require_viewer
    from app.main import app

    admin_user = _make_admin_user()
    app.dependency_overrides[require_admin] = lambda: admin_user
    app.dependency_overrides[require_viewer] = lambda: admin_user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def viewer_client() -> TestClient:
    """viewer 権限で認証済みのテストクライアント。"""
    from app.auth.dependencies import require_admin, require_viewer
    from app.main import app

    viewer_user = _make_viewer_user()
    app.dependency_overrides[require_viewer] = lambda: viewer_user
    app.dependency_overrides[require_admin] = lambda: _raise_403()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client() -> TestClient:
    """未認証のテストクライアント（dependency_overrides なし）。"""
    from app.auth.dependencies import require_admin, require_viewer
    from app.main import app

    def _raise_401() -> None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app.dependency_overrides[require_viewer] = lambda: _raise_401()
    app.dependency_overrides[require_admin] = lambda: _raise_401()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ── GET /api/aave/emode ───────────────────────────────────────────────────


class TestGetEmode:
    """GET /api/aave/emode のテスト。"""

    def test_get_emode_viewer_ok(
        self, viewer_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """viewer 以上は GET /api/aave/emode にアクセス可能。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        monkeypatch.setenv("AAVE_COLLATERAL_ASSETS", "USDC,USDT")
        stub = _StubAaveClient(hf=Decimal("2.5"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = viewer_client.get("/api/aave/emode")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_emode" in data
        assert "recommendation" in data
        assert data["current_emode"]["category_id"] == 0
        # USDC+USDT → cat1 推奨
        assert data["recommendation"]["recommended_category_id"] == 1
        # recommended_liquidation_threshold_bps が存在すること (M-2 修正確認)
        assert "recommended_liquidation_threshold_bps" in data["recommendation"]

    def test_get_emode_no_wallet_returns_cat0(
        self, viewer_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AAVE_WALLET_ADDRESS 未設定時は cat0 で fail-open。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        resp = viewer_client.get("/api/aave/emode")
        assert resp.status_code == 200
        assert resp.json()["current_emode"]["category_id"] == 0

    def test_get_emode_unauthenticated_401(self, unauth_client: TestClient) -> None:
        """認証なしは 401。"""
        resp = unauth_client.get("/api/aave/emode")
        assert resp.status_code == 401

    def test_get_emode_rpc_failure_fail_open(
        self, viewer_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RPC 失敗時は cat0 で fail-open（500 にならない）。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient()
        stub.get_user_emode = MagicMock(side_effect=AaveClientError("RPC down"))  # type: ignore[method-assign]
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = viewer_client.get("/api/aave/emode")
        assert resp.status_code == 200
        assert resp.json()["current_emode"]["category_id"] == 0


# ── POST /api/aave/emode ──────────────────────────────────────────────────


class TestSetEmode:
    """POST /api/aave/emode のテスト。"""

    def test_post_emode_viewer_returns_403(
        self, viewer_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """viewer では POST /api/aave/emode は 403。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        resp = viewer_client.post(
            "/api/aave/emode",
            json={"category_id": 1, "dry_run": True},
        )
        assert resp.status_code in (401, 403)

    def test_post_emode_no_wallet_503(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AAVE_WALLET_ADDRESS 未設定時は 503。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        resp = admin_client.post(
            "/api/aave/emode",
            json={"category_id": 1, "dry_run": True},
        )
        assert resp.status_code == 503

    def test_post_emode_dry_run_admin_ok(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """admin + dry_run=True は 200 を返し tx_hash=None・set_emode_tx=None。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient(hf=Decimal("2.5"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = admin_client.post(
                "/api/aave/emode",
                json={"category_id": 1, "dry_run": True},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["tx_hash"] is None
        assert data["set_emode_tx"] is None
        assert data["category_id"] == 1

    def test_post_emode_execute_returns_tx_hash(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dry_run=False 時はサーバー側で署名・送信まで完結し tx_hash が返る。

        2026-07-03 修正: 以前は set_emode_tx（未署名 tx）を返すだけで、
        「フロントエンドで署名・送信してください」という誤解を招く message を
        表示しながら実際には何も実行されない gap があった（棚卸しで検出）。
        admin 限定のプラットフォーム運用ウォレット操作であり、ユーザー個別資金は
        動かさないため、deposit/withdraw と同型のサーバー側署名で完結させる。
        """
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient(hf=Decimal("2.5"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = admin_client.post(
                "/api/aave/emode",
                json={"category_id": 1, "dry_run": False},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is False
        assert data["tx_hash"] == "0xstub_set_emode_hash"
        assert data["category_id"] == 1
        # 後方互換フィールドは常に None（サーバー側で送信完結するため未署名 tx は返さない）
        assert data["set_emode_tx"] is None

    def test_post_emode_hf_below_threshold_409(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HF < 1.6 の場合は 409 でブロック (M-1 修正確認)。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient(hf=Decimal("1.5"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = admin_client.post(
                "/api/aave/emode",
                json={"category_id": 1, "dry_run": False},
            )
        assert resp.status_code == 409
        assert "1.5" in resp.json()["detail"]

    def test_post_emode_hf_exactly_16_passes(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HF = 1.6 ちょうどは通過する（境界値テスト）。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient(hf=Decimal("1.6"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = admin_client.post(
                "/api/aave/emode",
                json={"category_id": 1, "dry_run": True},
            )
        assert resp.status_code == 200

    def test_post_emode_hf_inf_passes(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HF = inf (ポジションなし) は通過する。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xWALLET")
        stub = _StubAaveClient(hf=Decimal("inf"), emode_id=0)
        with patch("app.aave.router.get_default_aave_client", return_value=stub):
            resp = admin_client.post(
                "/api/aave/emode",
                json={"category_id": 1, "dry_run": True},
            )
        assert resp.status_code == 200

    def test_post_emode_unauthenticated_401(self, unauth_client: TestClient) -> None:
        """認証なしは 401。"""
        resp = unauth_client.post("/api/aave/emode", json={"category_id": 1})
        assert resp.status_code == 401
