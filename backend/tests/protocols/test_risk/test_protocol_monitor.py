"""ProtocolMonitor のユニットテスト。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.risk.protocol_monitor import ProtocolMonitor
from app.protocols.risk.schemas import ProtocolHealth, RiskLevel


class TestCheckAaveHealth:
    @pytest.mark.asyncio
    async def test_aave_health_returns_low_risk(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_aave_health()
        assert result.risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_aave_health_is_operational(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_aave_health()
        assert result.is_operational is True

    @pytest.mark.asyncio
    async def test_aave_health_tvl_is_decimal(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_aave_health()
        assert isinstance(result.tvl_usd, Decimal)

    @pytest.mark.asyncio
    async def test_aave_health_last_checked_is_datetime(
        self, protocol_monitor: ProtocolMonitor
    ) -> None:
        result = await protocol_monitor.check_aave_health()
        assert isinstance(result.last_checked, datetime)

    @pytest.mark.asyncio
    async def test_aave_health_protocol_name(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_aave_health()
        assert result.protocol == "aave"


class TestCheckLidoHealth:
    @pytest.mark.asyncio
    async def test_lido_health_low_risk_normal(self, protocol_monitor: ProtocolMonitor) -> None:
        """正常な APR とペグのとき LOW リスクを返す。"""
        result = await protocol_monitor.check_lido_health()
        assert result.risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_lido_health_high_risk_peg_deviation(
        self, mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
    ) -> None:
        """ペグ乖離 > 2% のとき HIGH リスクを返す。"""
        mock_lido_client.get_steth_eth_ratio.return_value = Decimal("0.97")  # 3% 乖離
        mock_lido_client.get_staking_apr.return_value = Decimal("3.5")
        monitor = ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)
        result = await monitor.check_lido_health()
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @pytest.mark.asyncio
    async def test_lido_health_critical_apr_negative(
        self, mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
    ) -> None:
        """APR < 0% のとき CRITICAL リスクを返す。"""
        mock_lido_client.get_staking_apr.return_value = Decimal("-1.0")
        mock_lido_client.get_steth_eth_ratio.return_value = Decimal("1.0")
        monitor = ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)
        result = await monitor.check_lido_health()
        assert result.risk_level == RiskLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_lido_health_critical_apr_too_high(
        self, mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
    ) -> None:
        """APR > 20% のとき CRITICAL リスクを返す。"""
        mock_lido_client.get_staking_apr.return_value = Decimal("25.0")
        mock_lido_client.get_steth_eth_ratio.return_value = Decimal("1.0")
        monitor = ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)
        result = await monitor.check_lido_health()
        assert result.risk_level == RiskLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_lido_health_tvl_is_decimal(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_lido_health()
        assert isinstance(result.tvl_usd, Decimal)

    @pytest.mark.asyncio
    async def test_lido_health_is_operational(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_lido_health()
        assert result.is_operational is True


class TestCheckPendleHealth:
    @pytest.mark.asyncio
    async def test_pendle_health_low_risk_normal(self, protocol_monitor: ProtocolMonitor) -> None:
        """正常なマーケットのとき LOW リスクを返す。"""
        result = await protocol_monitor.check_pendle_health()
        assert result.risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_pendle_health_medium_high_apy(
        self, mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
    ) -> None:
        """implied APY > 50% のとき MEDIUM リスクを返す。"""
        from datetime import timedelta, timezone

        maturity = datetime.now(timezone.utc) + timedelta(days=30)
        market_info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=30,
            implied_apy=Decimal("55.0"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        mock_pendle_client.get_market_info.return_value = market_info
        monitor = ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)
        result = await monitor.check_pendle_health()
        assert result.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_pendle_health_high_risk_low_tvl(
        self, mock_lido_client: AsyncMock, mock_pendle_client: AsyncMock
    ) -> None:
        """TVL < $1M のとき HIGH リスクを返す。"""
        from datetime import timedelta, timezone

        maturity = datetime.now(timezone.utc) + timedelta(days=30)
        market_info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=30,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("500000"),  # $500K < $1M
        )
        mock_pendle_client.get_market_info.return_value = market_info
        monitor = ProtocolMonitor(lido_client=mock_lido_client, pendle_client=mock_pendle_client)
        result = await monitor.check_pendle_health()
        assert result.risk_level == RiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_pendle_health_tvl_is_decimal(self, protocol_monitor: ProtocolMonitor) -> None:
        result = await protocol_monitor.check_pendle_health()
        assert isinstance(result.tvl_usd, Decimal)

    @pytest.mark.asyncio
    async def test_pendle_health_last_checked_is_datetime(
        self, protocol_monitor: ProtocolMonitor
    ) -> None:
        result = await protocol_monitor.check_pendle_health()
        assert isinstance(result.last_checked, datetime)


class TestCheckAll:
    @pytest.mark.asyncio
    async def test_check_all_returns_three_entries(self, protocol_monitor: ProtocolMonitor) -> None:
        """check_all は 3 件のプロトコルヘルス情報を返す。"""
        results = await protocol_monitor.check_all()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_check_all_returns_protocol_health_list(
        self, protocol_monitor: ProtocolMonitor
    ) -> None:
        results = await protocol_monitor.check_all()
        for item in results:
            assert isinstance(item, ProtocolHealth)

    @pytest.mark.asyncio
    async def test_check_all_covers_all_protocols(self, protocol_monitor: ProtocolMonitor) -> None:
        results = await protocol_monitor.check_all()
        protocols = {r.protocol for r in results}
        assert protocols == {"aave", "lido", "pendle"}
