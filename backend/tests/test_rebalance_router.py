# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rebalance_router.py

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.aave.rebalance_router import get_rebalance_service
from app.aave.rebalance_schemas import (
    AssetAllocation,
    RebalanceExecutionStatus,
    RebalanceHistoryEntry,
    RebalanceProposal,
    RebalanceResult,
    RebalanceStatusResponse,
)
from app.aave.schemas import AaveOperationResult, AaveOperationStatus, AaveOperationType
from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import UserRole
from app.main import create_app

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_admin_user() -> MagicMock:
    """テスト用 admin ユーザーを返す。"""
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


def _make_viewer_user() -> MagicMock:
    """テスト用 viewer ユーザーを返す。"""
    user = MagicMock()
    user.id = 2
    user.email = "viewer@example.com"
    user.username = "viewer"
    user.role = UserRole.VIEWER.value
    user.is_active = True
    return user


def _make_allocation(symbol: str = "USDC") -> AssetAllocation:
    return AssetAllocation(
        asset_symbol=symbol,
        current_amount_usd=Decimal("1000"),
        current_pct=Decimal("50"),
        target_pct=Decimal("50"),
        deviation_pct=Decimal("0"),
    )


def _make_status_response() -> RebalanceStatusResponse:
    alloc = _make_allocation()
    return RebalanceStatusResponse(
        current_allocations=[alloc],
        target_allocations=[alloc],
        health_factor=Decimal("2.5"),
        total_value_usd=Decimal("2000"),
        deviation_threshold_pct=Decimal("5"),
        needs_rebalance=False,
        last_rebalance_at=None,
        cooldown_remaining_seconds=0,
    )


def _make_proposal() -> RebalanceProposal:
    return RebalanceProposal(
        proposal_id="test-proposal-id-001",
        created_at=datetime(2026, 3, 12, 0, 0, 0, tzinfo=timezone.utc),
        health_factor_before=Decimal("2.5"),
        total_value_usd=Decimal("2000"),
        allocations=[_make_allocation()],
        operations=[],
        estimated_health_factor_after=Decimal("2.5"),
        max_single_trade_pct=Decimal("10"),
        confirmation_token="valid-token-abc",
        is_executable=True,
        rejection_reasons=[],
    )


def _make_result() -> RebalanceResult:
    return RebalanceResult(
        proposal_id="test-proposal-id-001",
        executed_at=datetime(2026, 3, 12, 0, 1, 0, tzinfo=timezone.utc),
        operations=[
            AaveOperationResult(
                operation=AaveOperationType.DEPOSIT,
                status=AaveOperationStatus.SUCCESS,
                asset_symbol="USDC",
                amount=Decimal("100"),
                tx_hash="0xdeadbeef",
                message="ok",
            )
        ],
        health_factor_before=Decimal("2.5"),
        health_factor_after=Decimal("2.6"),
        status=RebalanceExecutionStatus.SUCCESS,
        message="Rebalance completed",
    )


def _make_history_entry() -> RebalanceHistoryEntry:
    return RebalanceHistoryEntry(
        proposal_id="test-proposal-id-001",
        created_at=datetime(2026, 3, 12, 0, 0, 0, tzinfo=timezone.utc),
        executed_at=datetime(2026, 3, 12, 0, 1, 0, tzinfo=timezone.utc),
        status=RebalanceExecutionStatus.SUCCESS,
        total_value_usd=Decimal("2000"),
        operations_count=1,
        health_factor_before=Decimal("2.5"),
        health_factor_after=Decimal("2.6"),
    )


# ---------------------------------------------------------------------------
# ダミーサービス
# ---------------------------------------------------------------------------


class DummyRebalanceService:
    """テスト用ダミーの RebalanceService。"""

    def get_current_status(self) -> RebalanceStatusResponse:
        return _make_status_response()

    def simulate(self) -> RebalanceProposal:
        return _make_proposal()

    def execute(self, proposal_id: str, confirmation_token: str) -> RebalanceResult:
        if confirmation_token != "valid-token-abc":
            raise ValueError(f"Invalid confirmation token: {confirmation_token}")
        return _make_result()

    def get_history(self, limit: int = 20) -> list[RebalanceHistoryEntry]:
        return [_make_history_entry()] * min(limit, 3)


def _create_client(
    service: object | None = None,
    override_auth: bool = True,
) -> TestClient:
    """TestClient を生成する。service=None の場合は dependency_overrides を設定しない。"""
    admin_user = _make_admin_user()
    app = create_app()
    if service is not None:
        app.dependency_overrides[get_rebalance_service] = lambda: service
    if override_auth:
        app.dependency_overrides[require_admin] = lambda: admin_user
        app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# テスト: GET /aave/rebalance/status
# ---------------------------------------------------------------------------


def test_rebalance_status_returns_200() -> None:
    """GET /aave/rebalance/status が 200 と正しいスキーマを返す。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    resp = client.get("/api/aave/rebalance/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "health_factor" in data
    assert "needs_rebalance" in data
    assert "current_allocations" in data
    assert "cooldown_remaining_seconds" in data
    assert data["needs_rebalance"] is False


# ---------------------------------------------------------------------------
# テスト: POST /aave/rebalance/simulate
# ---------------------------------------------------------------------------


def test_rebalance_simulate_returns_200_with_proposal() -> None:
    """POST /aave/rebalance/simulate が 200 と proposal を返す。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    resp = client.post("/api/aave/rebalance/simulate")

    assert resp.status_code == 200
    data = resp.json()
    assert "proposal" in data
    proposal = data["proposal"]
    assert proposal["proposal_id"] == "test-proposal-id-001"
    assert "confirmation_token" in proposal
    assert "is_executable" in proposal


# ---------------------------------------------------------------------------
# テスト: POST /aave/rebalance/execute
# ---------------------------------------------------------------------------


def test_rebalance_execute_returns_200_on_valid_request() -> None:
    """POST /aave/rebalance/execute が有効なトークンで 200 を返す。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    payload = {
        "proposal_id": "test-proposal-id-001",
        "confirmation_token": "valid-token-abc",
    }

    resp = client.post("/api/aave/rebalance/execute", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    result = data["result"]
    assert result["proposal_id"] == "test-proposal-id-001"
    assert result["status"] == RebalanceExecutionStatus.SUCCESS.value


def test_rebalance_execute_returns_400_on_invalid_token() -> None:
    """POST /aave/rebalance/execute が無効なトークンで 400 を返す。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    payload = {
        "proposal_id": "test-proposal-id-001",
        "confirmation_token": "WRONG-TOKEN",
    }

    resp = client.post("/api/aave/rebalance/execute", json=payload)

    assert resp.status_code == 400
    assert "Invalid confirmation token" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# テスト: GET /aave/rebalance/history
# ---------------------------------------------------------------------------


def test_rebalance_history_returns_200_with_list() -> None:
    """GET /aave/rebalance/history が 200 とリストを返す。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    resp = client.get("/api/aave/rebalance/history")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    entry = data[0]
    assert "proposal_id" in entry
    assert "status" in entry
    assert "total_value_usd" in entry


def test_rebalance_history_respects_limit_param() -> None:
    """GET /aave/rebalance/history?limit=5 が limit パラメータを尊重する。"""
    service = DummyRebalanceService()
    client = _create_client(service)

    resp = client.get("/api/aave/rebalance/history?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    # ダミーサービスは min(limit, 3) 件を返すので 3 件
    assert len(data) <= 5


# ---------------------------------------------------------------------------
# テスト: 認証なしで全エンドポイントが 401/403 を返す
# ---------------------------------------------------------------------------


def test_status_requires_admin_auth() -> None:
    """GET /aave/rebalance/status は admin 認証なしで 401/403 を返す。"""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/aave/rebalance/status")

    assert resp.status_code in (401, 403)


def test_simulate_requires_admin_auth() -> None:
    """POST /aave/rebalance/simulate は admin 認証なしで 401/403 を返す。"""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/aave/rebalance/simulate")

    assert resp.status_code in (401, 403)


def test_execute_requires_admin_auth() -> None:
    """POST /aave/rebalance/execute は admin 認証なしで 401/403 を返す。"""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    payload = {
        "proposal_id": "test-proposal-id-001",
        "confirmation_token": "valid-token-abc",
    }

    resp = client.post("/api/aave/rebalance/execute", json=payload)

    assert resp.status_code in (401, 403)


def test_history_requires_admin_auth() -> None:
    """GET /aave/rebalance/history は admin 認証なしで 401/403 を返す。"""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/aave/rebalance/history")

    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# テスト: viewer ロールによるアクセス制御
# ---------------------------------------------------------------------------


def test_rebalance_status_accessible_by_viewer() -> None:
    """GET /api/aave/rebalance/status は viewer ロールでも 200 を返す。"""
    viewer_user = _make_viewer_user()
    service = DummyRebalanceService()
    app = create_app()
    app.dependency_overrides[get_rebalance_service] = lambda: service
    app.dependency_overrides[require_viewer] = lambda: viewer_user
    client = TestClient(app)

    resp = client.get("/api/aave/rebalance/status")

    assert resp.status_code == 200
    assert "health_factor" in resp.json()


def test_rebalance_execute_requires_admin_for_viewer() -> None:
    """POST /api/aave/rebalance/execute は viewer ロールでは 401/403 になる。"""
    viewer_user = _make_viewer_user()
    app = create_app()
    app.dependency_overrides[require_viewer] = lambda: viewer_user
    client = TestClient(app, raise_server_exceptions=False)

    payload = {
        "proposal_id": "test-proposal-id-001",
        "confirmation_token": "valid-token-abc",
    }
    resp = client.post("/api/aave/rebalance/execute", json=payload)

    assert resp.status_code in (401, 403)