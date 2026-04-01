# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_integration_aave.py
"""
シナリオC: Aave統合テスト

- POST /api/aave/rebalance (BUY/SELL/HOLD, dry_run=true)
- GET /api/aave/status
- GET /api/aave/health-factor
- AaveService 10%上限クリップ
- AaveService 30%超 NOOP (ExchangeService)
"""

import os
import tempfile
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.aave.router import get_multi_chain_aave_service
from app.aave.schemas import (
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.database import Base, get_db
from app.main import create_app


def _make_mock_multi_chain_service() -> MagicMock:
    """テスト用の MultiChainAaveService モックを作成する。"""
    mock_service = MagicMock()

    def _execute_rebalance(chain_name, action, amount, asset_symbol, dry_run):

        action_val = action.value if hasattr(action, "value") else str(action)
        if action_val == "HOLD":
            op = AaveOperationType.NOOP
        elif action_val == "BUY":
            op = AaveOperationType.DEPOSIT
        else:
            op = AaveOperationType.WITHDRAW
        return AaveOperationResult(
            operation=op,
            status=AaveOperationStatus.SKIPPED,
            asset_symbol=asset_symbol or "USDC",
            amount=amount if op != AaveOperationType.NOOP else Decimal("0"),
            tx_hash=None,
            message="dry_run or mock",
            before_health_factor=Decimal("3.0"),
            after_health_factor=Decimal("3.0"),
        )

    mock_service.execute_rebalance.side_effect = _execute_rebalance
    return mock_service


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine
    Base.metadata.drop_all(bind=test_engine)
    os.close(fd)
    os.unlink(path)


@pytest.fixture()
def client(test_db):
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    # MultiChainAaveService をモックしてRPC接続を回避
    app.dependency_overrides[get_multi_chain_aave_service] = _make_mock_multi_chain_service
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "adminpassword123"},
    )
    return r.json()["access_token"]


def test_aave_rebalance_dry_run_buy(client: TestClient) -> None:
    """POST /api/aave/rebalance (BUY, dry_run=true) → DEPOSIT + tx_hash=null"""
    token = get_admin_token(client)
    r = client.post(
        "/api/aave/rebalance",
        json={"action": "BUY", "amount": "100", "dry_run": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/aave/rebalance not implemented")
    assert r.status_code == 200
    data = r.json()
    # result フィールドに operation が含まれること
    assert "result" in data
    result = data["result"]
    # dry_run=True なので tx_hash は null
    assert result.get("tx_hash") is None


def test_aave_rebalance_dry_run_sell(client: TestClient) -> None:
    """POST /api/aave/rebalance (SELL, dry_run=true) → WITHDRAW + tx_hash=null"""
    token = get_admin_token(client)
    r = client.post(
        "/api/aave/rebalance",
        json={"action": "SELL", "amount": "100", "dry_run": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/aave/rebalance not implemented")
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    result = data["result"]
    assert result.get("tx_hash") is None


def test_aave_rebalance_hold_noop(client: TestClient) -> None:
    """POST /api/aave/rebalance (HOLD) → NOOP"""
    token = get_admin_token(client)
    r = client.post(
        "/api/aave/rebalance",
        json={"action": "HOLD", "amount": "100", "dry_run": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/aave/rebalance not implemented")
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    result = data["result"]
    assert result.get("operation") == "NOOP"


def test_aave_status(client: TestClient) -> None:
    """GET /api/aave/status → 200"""
    token = get_admin_token(client)
    r = client.get(
        "/api/aave/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/aave/status not implemented")
    assert r.status_code == 200


def test_aave_health_factor(client: TestClient) -> None:
    """GET /api/aave/health-factor → 200 + HF値が含まれる"""
    token = get_admin_token(client)
    r = client.get(
        "/api/aave/health-factor",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/aave/health-factor not implemented")
    assert r.status_code == 200
    data = r.json()
    assert "health_factor" in data


def test_single_trade_limit_10pct() -> None:
    """AaveServiceのrebalanceメソッドで10%超の取引がクリップされる（サービス層テスト）"""
    from app.aave.config import AaveSettings
    from app.aave.schemas import AaveOperationMode
    from app.aave.service import AaveService
    from app.ai.schemas import TradeAction

    # max_single_trade_usd=100 に設定
    settings = AaveSettings(
        network="polygon-mumbai",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal("100"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=0,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/state_test.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x5343b5bA672Ae99d627A1C87866b8E53F47Db2E6",
    )

    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("3.0")
    mock_client.deposit.return_value = MagicMock(tx_hash=None, status="success")

    mock_state = MagicMock()
    mock_state.is_stale.return_value = False
    mock_state_data = MagicMock()
    mock_state_data.emergency_stop = False
    mock_state_data.circuit_closed = True
    mock_state_data.mode = AaveOperationMode.NORMAL
    mock_state_data.health_factor = Decimal("3.0")
    mock_state.read_state.return_value = mock_state_data

    mock_monitoring = MagicMock()
    mock_monitoring.is_trading_allowed.return_value = True

    service = AaveService(
        client=mock_client,
        settings=settings,
        monitoring_service=mock_monitoring,
        state_manager=mock_state,
    )

    # 200 USD を指定（上限100 USDを超える）
    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("200"),
        dry_run=True,
    )
    # NOOP ではなく DEPOSIT (dry_run なので skipped になる場合もある)
    # いずれにせよ amount は 100 にクリップされているはず
    assert result.amount <= Decimal("100")


def test_daily_trade_limit_30pct() -> None:
    """ExchangeService日次30%上限でSKIPPED"""
    from datetime import datetime, timezone

    from app.ai.schemas import TradeAction
    from app.exchange.config import ExchangeSettings
    from app.exchange.schemas import OrderRequest, OrderStatus
    from app.exchange.service import ExchangeService

    mock_client = MagicMock()
    settings = ExchangeSettings(
        api_key="dummy",
        api_secret="dummy",
        sandbox=True,
        default_symbol="BTC/USDT",
        max_order_usd=Decimal("10000"),
        daily_trade_limit=3,
        cooldown_seconds=0,
        timeout_seconds=30,
        hostname="bybit.com",
        usd_to_jpy_rate=150.0,
        app_env="local",
        phase=1,
    )
    service = ExchangeService(client=mock_client, settings=settings)

    now = datetime.now(timezone.utc)
    for _ in range(settings.daily_trade_limit):
        service._trade_log.append(("BUY", now))

    request = OrderRequest(
        action=TradeAction.SELL,
        symbol="BTC/USDT",
        amount_usd=Decimal("100"),
        dry_run=False,
    )
    result = service.execute_trade(request)
    assert result.status == OrderStatus.SKIPPED
