# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance FastAPI router integration test (DummyClient 契約検証).

Phase A-2 staging E2E の前提検証。
Gate 4 staging 実機検証は P0-1 (Asana GID 1214821930631284) fix 後に実施。
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# DummyClient を許可するため development モードで起動
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LIDO_SANDBOX", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-lido-integration")

from app.protocols.lido.router import router as lido_router  # noqa: E402


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(lido_router)
    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_make_app())


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
# POST /api/protocols/lido/claim
# ---------------------------------------------------------------------------


class TestLidoClaim:
    def test_claim_dry_run_default_true(self, client: TestClient) -> None:
        """request_id のみ送った場合 dry_run=True がデフォルトであること。"""
        res = client.post("/api/protocols/lido/claim", json={"request_id": 1})
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True

    def test_claim_dry_run_no_tx_hash(self, client: TestClient) -> None:
        """dry_run=True の場合 tx_hash=None であること。"""
        data = client.post(
            "/api/protocols/lido/claim", json={"request_id": 1, "dry_run": True}
        ).json()
        assert data["tx_hash"] is None

    def test_claim_operation_type(self, client: TestClient) -> None:
        """operation フィールドが 'CLAIM' であること。"""
        data = client.post("/api/protocols/lido/claim", json={"request_id": 1}).json()
        assert data["operation"] == "CLAIM"

    def test_claim_request_id_preserved(self, client: TestClient) -> None:
        """リクエストの request_id がレスポンスに保持されること。"""
        data = client.post("/api/protocols/lido/claim", json={"request_id": 42}).json()
        assert data["request_id"] == 42

    def test_claim_dry_run_false_returns_tx_hash(self, client: TestClient) -> None:
        """dry_run=False（DummyClient）で tx_hash が返ること。"""
        data = client.post(
            "/api/protocols/lido/claim", json={"request_id": 1, "dry_run": False}
        ).json()
        assert data["dry_run"] is False
        assert data["tx_hash"] is not None
        assert str(data["tx_hash"]).startswith("0x")

    def test_claim_rejects_zero_request_id(self, client: TestClient) -> None:
        """request_id=0 は 422 を返すこと。"""
        res = client.post("/api/protocols/lido/claim", json={"request_id": 0})
        assert res.status_code == 422

    def test_claim_rejects_negative_request_id(self, client: TestClient) -> None:
        """request_id=-1 は 422 を返すこと。"""
        res = client.post("/api/protocols/lido/claim", json={"request_id": -1})
        assert res.status_code == 422

    def test_claim_missing_request_id_is_422(self, client: TestClient) -> None:
        """request_id 未指定は 422 を返すこと。"""
        res = client.post("/api/protocols/lido/claim", json={})
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
