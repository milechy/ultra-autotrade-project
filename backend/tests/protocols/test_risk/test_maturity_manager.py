"""MaturityManager のユニットテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.risk.maturity_manager import MaturityManager
from app.protocols.risk.schemas import MaturityAlert, RiskLevel


class TestClassifyMaturityRisk:
    def test_30_days_returns_low_none(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(30)
        assert risk == RiskLevel.LOW
        assert action == "none"

    def test_31_days_returns_low_none(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(31)
        assert risk == RiskLevel.LOW
        assert action == "none"

    def test_100_days_returns_low_none(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(100)
        assert risk == RiskLevel.LOW
        assert action == "none"

    def test_29_days_returns_medium_monitor(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(29)
        assert risk == RiskLevel.MEDIUM
        assert action == "monitor"

    def test_14_days_returns_medium_monitor(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(14)
        assert risk == RiskLevel.MEDIUM
        assert action == "monitor"

    def test_13_days_returns_high_prepare_exit(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(13)
        assert risk == RiskLevel.HIGH
        assert action == "prepare_exit"

    def test_7_days_returns_high_prepare_exit(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(7)
        assert risk == RiskLevel.HIGH
        assert action == "prepare_exit"

    def test_6_days_returns_critical_exit_now(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(6)
        assert risk == RiskLevel.CRITICAL
        assert action == "exit_now"

    def test_0_days_returns_critical_exit_now(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(0)
        assert risk == RiskLevel.CRITICAL
        assert action == "exit_now"

    def test_1_day_returns_critical_exit_now(self, maturity_manager: MaturityManager) -> None:
        risk, action = maturity_manager.classify_maturity_risk(1)
        assert risk == RiskLevel.CRITICAL
        assert action == "exit_now"


class TestCheckMaturities:
    @pytest.mark.asyncio
    async def test_check_maturities_returns_list(self, maturity_manager: MaturityManager) -> None:
        result = await maturity_manager.check_maturities(["0x" + "0" * 40])
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_check_maturities_returns_maturity_alert(
        self, maturity_manager: MaturityManager
    ) -> None:
        result = await maturity_manager.check_maturities(["0x" + "0" * 40])
        assert isinstance(result[0], MaturityAlert)

    @pytest.mark.asyncio
    async def test_check_maturities_30_days_low_risk(
        self, maturity_manager: MaturityManager
    ) -> None:
        """30 日後満期のとき LOW リスクを返す。"""
        result = await maturity_manager.check_maturities(["0x" + "0" * 40])
        assert result[0].risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_check_maturities_critical_near_expiry(
        self, mock_pendle_client: AsyncMock
    ) -> None:
        """5 日後満期のとき CRITICAL リスクを返す。"""
        maturity = datetime.now(timezone.utc) + timedelta(days=5)
        market_info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=5,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        mock_pendle_client.get_market_info.return_value = market_info
        manager = MaturityManager(pendle_client=mock_pendle_client)
        result = await manager.check_maturities(["0x" + "0" * 40])
        assert result[0].risk_level == RiskLevel.CRITICAL
        assert result[0].action_required == "exit_now"

    @pytest.mark.asyncio
    async def test_check_maturities_days_remaining_is_int(
        self, maturity_manager: MaturityManager
    ) -> None:
        result = await maturity_manager.check_maturities(["0x" + "0" * 40])
        assert isinstance(result[0].days_remaining, int)


class TestGetExpiringPositions:
    @pytest.mark.asyncio
    async def test_get_expiring_positions_filters_correctly(
        self, maturity_manager: MaturityManager
    ) -> None:
        """30 日後満期のポジションは within_days=14 でフィルタされない。"""
        result = await maturity_manager.get_expiring_positions(within_days=14)
        # days_remaining=30 なので 14 日以内には含まれない
        assert all(a.days_remaining <= 14 for a in result)

    @pytest.mark.asyncio
    async def test_get_expiring_positions_includes_near_expiry(
        self, mock_pendle_client: AsyncMock
    ) -> None:
        """5 日後満期のポジションは within_days=14 に含まれる。"""
        maturity = datetime.now(timezone.utc) + timedelta(days=5)
        market_info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=5,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        mock_pendle_client.get_market_info.return_value = market_info
        manager = MaturityManager(pendle_client=mock_pendle_client)
        result = await manager.get_expiring_positions(within_days=14)
        assert len(result) == 1
        assert result[0].days_remaining <= 14
