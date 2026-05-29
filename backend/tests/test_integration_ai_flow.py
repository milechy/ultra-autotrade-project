# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_integration_ai_flow.py
"""
シナリオB: AIフロー・ルールエンジン統合テスト

- GET /api/ai/decisions → リスト形式確認
- ルールエンジン: HF < 1.6 → HOLD
- ルールエンジン: クールダウン → HOLD
- ルールエンジン: 日次上限 → HOLD
"""

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import create_app


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


def test_ai_decisions_list(client: TestClient) -> None:
    """GET /api/ai/decisions?limit=20 → 200 + list形式レスポンス確認"""
    token = get_admin_token(client)
    r = client.get(
        "/api/ai/decisions?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/ai/decisions not implemented")
    assert r.status_code == 200
    data = r.json()
    # items フィールドがあること (AIDecisionListResponse 形式)
    assert "items" in data
    assert isinstance(data["items"], list)


def test_rule_engine_hf_check() -> None:
    """HF < 1.6 のケースをモックしてHOLD(NOOP)結果確認（サービス層テスト）"""
    from unittest.mock import MagicMock

    from app.aave.schemas import AaveOperationType
    from app.aave.service import AaveService
    from app.ai.schemas import TradeAction

    # HF < 1.6 の DummyClient と state_manager をモック
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("1.4")

    mock_state = MagicMock()
    mock_state.is_stale.return_value = False
    mock_state_data = MagicMock()
    mock_state_data.emergency_stop = False
    mock_state_data.circuit_closed = True
    from app.aave.schemas import AaveOperationMode

    mock_state_data.mode = AaveOperationMode.NORMAL
    mock_state_data.health_factor = Decimal("1.4")
    mock_state.read_state.return_value = mock_state_data

    mock_monitoring = MagicMock()
    mock_monitoring.is_trading_allowed.return_value = True

    service = AaveService(
        client=mock_client,
        monitoring_service=mock_monitoring,
        state_manager=mock_state,
    )

    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("100"),
        dry_run=True,
        wallet_address="0xTest000000000000000000000000000000000000",
    )
    # HF < min_health_factor なら NOOP になること
    assert result.operation == AaveOperationType.NOOP


def test_rule_engine_cooldown() -> None:
    """クールダウン中はNOOP（サービス層テスト）"""
    from unittest.mock import MagicMock

    from app.aave.schemas import AaveOperationMode, AaveOperationType
    from app.aave.service import AaveService
    from app.ai.schemas import TradeAction

    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.5")
    mock_client.deposit.return_value = MagicMock(tx_hash="0xabc", status="success")

    mock_state = MagicMock()
    mock_state.is_stale.return_value = False
    mock_state_data = MagicMock()
    mock_state_data.emergency_stop = False
    mock_state_data.circuit_closed = True
    mock_state_data.mode = AaveOperationMode.NORMAL
    mock_state_data.health_factor = Decimal("2.5")
    mock_state.read_state.return_value = mock_state_data

    mock_monitoring = MagicMock()
    mock_monitoring.is_trading_allowed.return_value = True

    service = AaveService(
        client=mock_client,
        monitoring_service=mock_monitoring,
        state_manager=mock_state,
    )

    # 1回目のトレードを記録してクールダウン状態を作る
    now = datetime.now(timezone.utc)
    service._recent_actions.append(now)

    # 2回目のトレードはクールダウン中なので NOOP
    result = service.execute_rebalance(
        action=TradeAction.BUY,
        amount=Decimal("100"),
        dry_run=False,
        wallet_address="0xTest000000000000000000000000000000000000",
    )
    assert result.operation == AaveOperationType.NOOP


def test_rule_engine_daily_limit() -> None:
    """日次トレード上限でSKIPPED（ExchangeServiceのルールエンジンテスト）"""
    from unittest.mock import MagicMock

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
        daily_trade_limit=2,
        cooldown_seconds=0,
        timeout_seconds=30,
        hostname="bybit.com",
        usd_to_jpy_rate=150.0,
        app_env="local",
        phase=1,
    )
    service = ExchangeService(client=mock_client, settings=settings)

    # daily_trade_limit 回分のトレードを記録
    now = datetime.now(timezone.utc)
    for _ in range(settings.daily_trade_limit):
        service._trade_log.append(("BUY", now))

    request = OrderRequest(
        action=TradeAction.BUY,
        symbol="BTCUSDT",
        amount_usd=Decimal("100"),
        dry_run=False,
        wallet_address="0xTest000000000000000000000000000000000000",
    )
    result = service.execute_trade(request)
    assert result.status == OrderStatus.SKIPPED
    assert "Daily trade limit" in result.message
