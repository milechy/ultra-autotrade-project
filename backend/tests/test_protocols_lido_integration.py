# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance FastAPI router integration test (DummyClient 契約検証).

Phase A-2 staging E2E の前提検証。
Gate 4 staging 実機検証は P0-1 (Asana GID 1214821930631284) fix 後に実施。
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# DummyClient を許可するため development モードで起動
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LIDO_SANDBOX", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-lido-integration")

from app.auth.dependencies import require_admin  # noqa: E402
from app.auth.models import User, UserRole  # noqa: E402
from app.protocols.lido.router import router as lido_router  # noqa: E402

_app = FastAPI()
_app.include_router(lido_router)


def _fake_admin() -> User:
    """テスト用 admin ユーザー（require_admin override 用）。"""
    return User(id=1, email="admin@example.com", role=UserRole.ADMIN.value, is_active=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_app)


@pytest.fixture(autouse=True)
def _override_admin_auth() -> Generator[None, None, None]:
    """既定では admin 認証済みとして扱う（write エンドポイント正常系テスト用）。

    ef5bb42f で追加された require_admin に対応し、DummyClient 統合テストが
    401 で落ちないようにする。無認証 401 の確認は test_lido_router.py の
    TestWriteEndpointsRequireAdmin が担う。
    """
    _app.dependency_overrides[require_admin] = _fake_admin
    yield
    _app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/protocols/lido/status
# ---------------------------------------------------------------------------


class TestLidoStatus:
    def test_status_returns_200(self, client: TestClient) -> None:
        res = client.get("/api/protocols/lido/status")
        assert res.status_code == 200

    def test_status_required_fields_present(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/status").json()
        for field in (
            "steth_balance",
            "staking_apr",
            "steth_eth_ratio",
            "peg_deviation_pct",
            "chain",
            "sandbox",
        ):
            assert field in data, f"missing field: {field}"

    def test_status_sandbox_true(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/status").json()
        assert data["sandbox"] is True

    def test_status_chain_is_holesky(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/status").json()
        assert data["chain"] == "holesky"

    def test_status_no_float_values(self, client: TestClient) -> None:
        """Decimal フィールドが JSON で float ではなく文字列で返ること。"""
        data = client.get("/api/protocols/lido/status").json()
        for field in ("steth_balance", "staking_apr", "steth_eth_ratio", "peg_deviation_pct"):
            val = data[field]
            assert not isinstance(val, float), f"{field} is float (must be string)"
            Decimal(str(val))  # パース可能であること


# ---------------------------------------------------------------------------
# GET /api/protocols/lido/apr
# ---------------------------------------------------------------------------


class TestLidoApr:
    def test_apr_returns_200(self, client: TestClient) -> None:
        res = client.get("/api/protocols/lido/apr")
        assert res.status_code == 200

    def test_apr_fields_present(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/apr").json()
        assert "staking_apr" in data
        assert "source" in data

    def test_apr_dummy_value_is_3_5(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/apr").json()
        assert Decimal(str(data["staking_apr"])) == Decimal("3.5")

    def test_apr_source_is_dummy(self, client: TestClient) -> None:
        data = client.get("/api/protocols/lido/apr").json()
        assert data["source"] == "dummy"


# ---------------------------------------------------------------------------
# POST /api/protocols/lido/stake
# ---------------------------------------------------------------------------


class TestLidoStake:
    def test_stake_dry_run_default_true(self, client: TestClient) -> None:
        res = client.post("/api/protocols/lido/stake", json={"amount_eth": "0.1"})
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True

    def test_stake_dry_run_no_tx_hash(self, client: TestClient) -> None:
        data = client.post(
            "/api/protocols/lido/stake", json={"amount_eth": "0.1", "dry_run": True}
        ).json()
        assert data["tx_hash"] is None

    def test_stake_dry_run_response_fields(self, client: TestClient) -> None:
        data = client.post(
            "/api/protocols/lido/stake", json={"amount_eth": "0.5", "dry_run": True}
        ).json()
        assert data["operation"] == "STAKE"
        assert Decimal(str(data["amount_eth"])) == Decimal("0.5")
        assert Decimal(str(data["received_steth"])) == Decimal("0.5")
        assert Decimal(str(data["staking_apr"])) == Decimal("3.5")

    def test_stake_live_returns_tx_hash(self, client: TestClient) -> None:
        """dry_run=False でトランザクションハッシュが返ること（DummyClient）。"""
        data = client.post(
            "/api/protocols/lido/stake", json={"amount_eth": "0.01", "dry_run": False}
        ).json()
        assert data["dry_run"] is False
        assert data["tx_hash"] is not None
        assert str(data["tx_hash"]).startswith("0x")

    def test_stake_rejects_zero_amount(self, client: TestClient) -> None:
        res = client.post("/api/protocols/lido/stake", json={"amount_eth": "0"})
        assert res.status_code == 422

    def test_stake_rejects_negative_amount(self, client: TestClient) -> None:
        res = client.post("/api/protocols/lido/stake", json={"amount_eth": "-1"})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/protocols/lido/withdraw
# ---------------------------------------------------------------------------


class TestLidoWithdraw:
    def test_withdraw_dry_run_default_true(self, client: TestClient) -> None:
        res = client.post("/api/protocols/lido/withdraw", json={"amount_steth": "0.1"})
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True

    def test_withdraw_operation_type(self, client: TestClient) -> None:
        data = client.post("/api/protocols/lido/withdraw", json={"amount_steth": "0.5"}).json()
        assert data["operation"] == "WITHDRAW_REQUEST"

    def test_withdraw_dry_run_no_tx_hash(self, client: TestClient) -> None:
        data = client.post(
            "/api/protocols/lido/withdraw", json={"amount_steth": "0.1", "dry_run": True}
        ).json()
        assert data["tx_hash"] is None

    def test_withdraw_note_contains_claim_info(self, client: TestClient) -> None:
        data = client.post("/api/protocols/lido/withdraw", json={"amount_steth": "0.1"}).json()
        assert "note" in data
        assert data["note"]  # 空でないこと

    def test_withdraw_rejects_zero(self, client: TestClient) -> None:
        res = client.post("/api/protocols/lido/withdraw", json={"amount_steth": "0"})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/protocols/lido/claim（checkpoint hints 方式 / 複数形 request_ids）
# ---------------------------------------------------------------------------


class TestLidoClaim:
    def test_claim_dry_run_default_true(self, client: TestClient) -> None:
        """request_ids のみ送った場合 dry_run=True がデフォルトであること。"""
        res = client.post("/api/protocols/lido/claim", json={"request_ids": [1]})
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True

    def test_claim_dry_run_no_tx_hash(self, client: TestClient) -> None:
        """dry_run=True の場合 tx_hash=None であること。"""
        data = client.post(
            "/api/protocols/lido/claim", json={"request_ids": [1], "dry_run": True}
        ).json()
        assert data["tx_hash"] is None

    def test_claim_operation_type(self, client: TestClient) -> None:
        """operation フィールドが 'CLAIM' であること。"""
        data = client.post("/api/protocols/lido/claim", json={"request_ids": [1]}).json()
        assert data["operation"] == "CLAIM"

    def test_claim_request_ids_preserved(self, client: TestClient) -> None:
        """リクエストの request_ids がレスポンスに保持されること。"""
        data = client.post("/api/protocols/lido/claim", json={"request_ids": [42, 43]}).json()
        assert data["request_ids"] == [42, 43]

    def test_claim_dry_run_false_returns_tx_hash(self, client: TestClient) -> None:
        """dry_run=False（DummyClient）で tx_hash が返ること。"""
        data = client.post(
            "/api/protocols/lido/claim", json={"request_ids": [1, 2], "dry_run": False}
        ).json()
        assert data["dry_run"] is False
        assert data["tx_hash"] is not None
        assert str(data["tx_hash"]).startswith("0x")

    def test_claim_multiple_request_ids(self, client: TestClient) -> None:
        """複数の request_ids を一括クレームできること。"""
        data = client.post(
            "/api/protocols/lido/claim", json={"request_ids": [100, 200, 300], "dry_run": True}
        ).json()
        assert data["request_ids"] == [100, 200, 300]

    def test_claim_empty_request_ids_is_422(self, client: TestClient) -> None:
        """request_ids が空リストは 422 を返すこと（min_length=1）。"""
        res = client.post("/api/protocols/lido/claim", json={"request_ids": []})
        assert res.status_code == 422

    def test_claim_missing_request_ids_is_422(self, client: TestClient) -> None:
        """request_ids 未指定は 422 を返すこと。"""
        res = client.post("/api/protocols/lido/claim", json={})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/protocols/lido/withdrawal-status
# ---------------------------------------------------------------------------


class TestLidoWithdrawalStatus:
    def test_withdrawal_status_returns_200(self, client: TestClient) -> None:
        """request_ids クエリパラメータ付きで 200 が返ること。"""
        res = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1,2"},
        )
        assert res.status_code == 200

    def test_withdrawal_status_fields_present(self, client: TestClient) -> None:
        """request_ids と statuses フィールドが存在すること。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1,2"},
        ).json()
        assert "request_ids" in data
        assert "statuses" in data

    def test_withdrawal_status_returns_correct_count(self, client: TestClient) -> None:
        """指定した request_ids の件数と statuses の件数が一致すること。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1,2,3"},
        ).json()
        assert len(data["statuses"]) == 3

    def test_withdrawal_status_status_fields(self, client: TestClient) -> None:
        """各ステータスに必須フィールドが含まれること。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1"},
        ).json()
        status = data["statuses"][0]
        for field in (
            "request_id",
            "amount_of_steth",
            "is_finalized",
            "is_claimed",
            "owner",
            "timestamp",
        ):
            assert field in status, f"missing field: {field}"

    def test_withdrawal_status_dummy_is_finalized(self, client: TestClient) -> None:
        """DummyClient は is_finalized=True を返すこと。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1"},
        ).json()
        assert data["statuses"][0]["is_finalized"] is True

    def test_withdrawal_status_no_float(self, client: TestClient) -> None:
        """Decimal フィールドが JSON で float ではなく文字列で返ること。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "1"},
        ).json()
        status = data["statuses"][0]
        for field in ("amount_of_steth", "amount_of_shares"):
            val = status[field]
            assert not isinstance(val, float), f"{field} is float (must be string)"
            Decimal(str(val))  # パース可能であること

    def test_withdrawal_status_missing_param_is_422(self, client: TestClient) -> None:
        """request_ids パラメータ未指定は 422 を返すこと。"""
        res = client.get("/api/protocols/lido/withdrawal-status")
        assert res.status_code == 422

    def test_withdrawal_status_invalid_ids_is_422(self, client: TestClient) -> None:
        """非数値の request_ids は 422 を返すこと。"""
        res = client.get(
            "/api/protocols/lido/withdrawal-status",
            params={"request_ids": "abc,xyz"},
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/protocols/lido/withdrawal-requests
# ---------------------------------------------------------------------------


class TestLidoWithdrawalRequests:
    def test_withdrawal_requests_returns_200(self, client: TestClient) -> None:
        """address クエリパラメータ付きで 200 が返ること。"""
        res = client.get(
            "/api/protocols/lido/withdrawal-requests",
            params={"address": "0x" + "aa" * 20},
        )
        assert res.status_code == 200

    def test_withdrawal_requests_fields_present(self, client: TestClient) -> None:
        """address と request_ids フィールドが存在すること。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-requests",
            params={"address": "0x" + "aa" * 20},
        ).json()
        assert "address" in data
        assert "request_ids" in data

    def test_withdrawal_requests_returns_list(self, client: TestClient) -> None:
        """request_ids がリストであること（DummyClient は固定値を返す）。"""
        data = client.get(
            "/api/protocols/lido/withdrawal-requests",
            params={"address": "0x" + "aa" * 20},
        ).json()
        assert isinstance(data["request_ids"], list)

    def test_withdrawal_requests_missing_address_is_422(self, client: TestClient) -> None:
        """address パラメータ未指定は 422 を返すこと。"""
        res = client.get("/api/protocols/lido/withdrawal-requests")
        assert res.status_code == 422
