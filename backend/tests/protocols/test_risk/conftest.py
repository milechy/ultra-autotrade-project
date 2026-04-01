"""Risk Engine テスト共有フィクスチャ。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.risk.auto_evacuate import AutoEvacuator
from app.protocols.risk.compound_risk import CompoundRiskAssessor
from app.protocols.risk.maturity_manager import MaturityManager
from app.protocols.risk.peg_monitor import PegMonitor
from app.protocols.risk.protocol_monitor import ProtocolMonitor


@pytest.fixture
def mock_lido_client() -> AsyncMock:
    """Lido クライアントのモック。stETH/ETH レート=1.0、APR=3.5%。"""
    client = AsyncMock()
    client.get_steth_eth_ratio.return_value = Decimal("1.0")
    client.get_staking_apr.return_value = Decimal("3.5")
    return client


@pytest.fixture
def mock_pendle_client() -> AsyncMock:
    """Pendle クライアントのモック。30日後満期、implied APY=5.2%、TVL=$50M。"""
    client = AsyncMock()
    maturity = datetime.now(timezone.utc) + timedelta(days=30)
    market_info = PendleMarketInfo(
        market_address="0x" + "0" * 40,
        underlying_asset="stETH",
        maturity=maturity,
        days_to_maturity=30,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal("0.95"),
        yt_price=Decimal("0.05"),
        tvl_usd=Decimal("50000000"),
    )
    client.get_market_info.return_value = market_info
    return client


@pytest.fixture
def protocol_monitor(mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock) -> ProtocolMonitor:
    """ProtocolMonitor インスタンス（モッククライアント使用）。"""
    return ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)


@pytest.fixture
def peg_monitor(mock_lido_client: AsyncMock) -> PegMonitor:
    """PegMonitor インスタンス（モッククライアント使用）。"""
    return PegMonitor(lido_client=mock_lido_client)


@pytest.fixture
def maturity_manager(mock_pendle_client: AsyncMock) -> MaturityManager:
    """MaturityManager インスタンス（モッククライアント使用）。"""
    return MaturityManager(pendle_client=mock_pendle_client)


@pytest.fixture
def compound_assessor(
    protocol_monitor: ProtocolMonitor,
    peg_monitor: PegMonitor,
    maturity_manager: MaturityManager,
) -> CompoundRiskAssessor:
    """CompoundRiskAssessor インスタンス（モックコンポーネント使用）。"""
    return CompoundRiskAssessor(
        protocol_monitor=protocol_monitor,
        peg_monitor=peg_monitor,
        maturity_manager=maturity_manager,
    )


@pytest.fixture
def evacuator() -> AutoEvacuator:
    """AutoEvacuator インスタンス。"""
    return AutoEvacuator()
