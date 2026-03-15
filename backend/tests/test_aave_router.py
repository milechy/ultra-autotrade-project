# backend/tests/test_aave_router.py

from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.aave.router import get_aave_service, get_multi_chain_aave_service
from app.aave.schemas import (
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import UserRole
from app.main import create_app


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


class DummyAaveService:
    """
    /aave/rebalance ルーター用のダミーサービス。

    呼び出し内容を記録しつつ、固定の結果を返す。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object, object]] = []

    def execute_rebalance(
        self,
        action,
        amount,
        asset_symbol=None,
        dry_run=False,
    ) -> AaveOperationResult:
        self.calls.append((action, amount, asset_symbol, dry_run))
        return AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=asset_symbol or "USDC",
            amount=Decimal(amount),
            tx_hash="dummy-tx",
            message="ok",
        )


class DummyMultiChainService:
    """
    /aave/rebalance ルーター用のマルチチェーンダミーサービス。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object, object, object]] = []

    def execute_rebalance(
        self,
        chain_name: str,
        action=None,
        amount=None,
        asset_symbol=None,
        dry_run=False,
    ) -> AaveOperationResult:
        self.calls.append((chain_name, action, amount, asset_symbol, dry_run))
        return AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=asset_symbol or "USDC",
            amount=Decimal(amount) if amount is not None else Decimal("0"),
            tx_hash="dummy-tx",
            message="ok",
            chain_name=chain_name,
        )

    def get_all_health_factors(self) -> dict:
        return {"arbitrum": Decimal("2.5"), "optimism": Decimal("1.8")}

    def get_chain_names(self) -> list:
        return ["arbitrum", "optimism"]


def _create_client_with_dummy_service(service: DummyAaveService) -> TestClient:
    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_aave_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: admin_user
    app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


def _create_client_with_multi_chain_service(service: DummyMultiChainService) -> TestClient:
    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_multi_chain_aave_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: admin_user
    app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


def test_aave_rebalance_buy_returns_200() -> None:
    service = DummyMultiChainService()
    client = _create_client_with_multi_chain_service(service)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
        "dry_run": False,
    }

    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["result"]["operation"] == "DEPOSIT"
    assert data["result"]["status"] == "success"
    assert service.calls  # at least 1 call
    # Default chain should be arbitrum
    assert service.calls[0][0] == "arbitrum"


def test_aave_rebalance_validation_error_for_negative_amount() -> None:
    # Pydantic バリデーションで 422 になるケース
    service = DummyMultiChainService()
    client = _create_client_with_multi_chain_service(service)

    payload = {
        "action": "BUY",
        "amount": "-1",  # gt=0 に違反
        "asset_symbol": "USDC",
    }

    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 422


def test_aave_rebalance_value_error_from_service_returns_400() -> None:
    class ErrorMultiChainService:
        def execute_rebalance(self, *args, **kwargs):
            raise ValueError("invalid amount")

    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_multi_chain_aave_service] = ErrorMultiChainService  # type: ignore[arg-type]
    app.dependency_overrides[require_admin] = lambda: admin_user
    client = TestClient(app)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
    }

    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 400
    assert "invalid amount" in resp.json()["detail"]


def test_aave_rebalance_unexpected_error_returns_500() -> None:
    class CrashMultiChainService:
        def execute_rebalance(self, *args, **kwargs):
            raise RuntimeError("boom")

    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_multi_chain_aave_service] = CrashMultiChainService  # type: ignore[arg-type]
    app.dependency_overrides[require_admin] = lambda: admin_user
    client = TestClient(app)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
    }

    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 500


def test_aave_rebalance_with_chain_name() -> None:
    """chain_name 指定時に正しいチェーンに委譲される。"""
    service = DummyMultiChainService()
    client = _create_client_with_multi_chain_service(service)

    payload = {
        "action": "SELL",
        "amount": "25",
        "asset_symbol": "USDC",
        "chain_name": "optimism",
    }

    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 200
    assert service.calls[0][0] == "optimism"


def test_aave_chains_health_returns_200() -> None:
    """GET /aave/chains/health が全チェーンの HF を返す。"""
    service = DummyMultiChainService()
    client = _create_client_with_multi_chain_service(service)

    resp = client.get("/api/aave/chains/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "chains" in data
    assert "arbitrum" in data["chains"]
    assert "optimism" in data["chains"]


def test_aave_chains_health_accessible_by_viewer() -> None:
    """GET /api/aave/chains/health は viewer ロールでも 200 を返す。"""
    viewer_user = _make_viewer_user()
    service = DummyMultiChainService()
    app = create_app()
    app.dependency_overrides[get_multi_chain_aave_service] = lambda: service
    app.dependency_overrides[require_viewer] = lambda: viewer_user
    client = TestClient(app)

    resp = client.get("/api/aave/chains/health")
    assert resp.status_code == 200
    assert "chains" in resp.json()


def test_aave_rebalance_requires_admin_for_viewer() -> None:
    """POST /api/aave/rebalance は viewer ロールでは 403 になる。"""
    viewer_user = _make_viewer_user()
    app = create_app()
    app.dependency_overrides[require_viewer] = lambda: viewer_user
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"action": "BUY", "amount": "10", "asset_symbol": "USDC"}
    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code in (401, 403)
