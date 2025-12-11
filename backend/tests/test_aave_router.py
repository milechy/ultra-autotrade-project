# backend/tests/test_aave_router.py

from decimal import Decimal

from fastapi.testclient import TestClient

from app.aave.router import get_aave_service
from app.aave.schemas import (
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.main import create_app


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


def _create_client_with_dummy_service(service: DummyAaveService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_aave_service] = lambda: service
    return TestClient(app)


def test_aave_rebalance_buy_returns_200() -> None:
    service = DummyAaveService()
    client = _create_client_with_dummy_service(service)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
        "dry_run": False,
    }

    resp = client.post("/aave/rebalance", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["result"]["operation"] == "DEPOSIT"
    assert data["result"]["status"] == "success"
    assert service.calls  # 少なくとも 1 回は呼ばれていること


def test_aave_rebalance_validation_error_for_negative_amount() -> None:
    # Pydantic バリデーションで 422 になるケース
    client = TestClient(create_app())

    payload = {
        "action": "BUY",
        "amount": "-1",  # gt=0 に違反
        "asset_symbol": "USDC",
    }

    resp = client.post("/aave/rebalance", json=payload)
    assert resp.status_code == 422


def test_aave_rebalance_value_error_from_service_returns_400() -> None:
    class ErrorService:
        def execute_rebalance(self, *args, **kwargs):
            raise ValueError("invalid amount")

    app = create_app()
    app.dependency_overrides[get_aave_service] = ErrorService  # type: ignore[arg-type]
    client = TestClient(app)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
    }

    resp = client.post("/aave/rebalance", json=payload)
    assert resp.status_code == 400
    assert "invalid amount" in resp.json()["detail"]


def test_aave_rebalance_unexpected_error_returns_500() -> None:
    class CrashService:
        def execute_rebalance(self, *args, **kwargs):
            raise RuntimeError("boom")

    app = create_app()
    app.dependency_overrides[get_aave_service] = CrashService  # type: ignore[arg-type]
    client = TestClient(app)

    payload = {
        "action": "BUY",
        "amount": "10",
        "asset_symbol": "USDC",
    }

    resp = client.post("/aave/rebalance", json=payload)
    assert resp.status_code == 500
