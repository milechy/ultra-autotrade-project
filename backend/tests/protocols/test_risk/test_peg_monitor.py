"""PegMonitor のユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.risk.peg_monitor import PegMonitor
from app.protocols.risk.schemas import PegStatus, RiskLevel


class TestClassifyRisk:
    def test_deviation_under_0_5_returns_low(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("0.4"))
        assert result == RiskLevel.LOW

    def test_deviation_zero_returns_low(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("0"))
        assert result == RiskLevel.LOW

    def test_deviation_0_5_returns_medium(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("0.5"))
        assert result == RiskLevel.MEDIUM

    def test_deviation_0_75_returns_medium(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("0.75"))
        assert result == RiskLevel.MEDIUM

    def test_deviation_1_0_returns_high(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("1.0"))
        assert result == RiskLevel.HIGH

    def test_deviation_1_5_returns_high(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("1.5"))
        assert result == RiskLevel.HIGH

    def test_deviation_2_0_returns_critical(self, peg_monitor: PegMonitor) -> None:
        """境界値 2.0% → CRITICAL。"""
        result = peg_monitor.classify_risk(Decimal("2.0"))
        assert result == RiskLevel.CRITICAL

    def test_deviation_2_5_returns_critical(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("2.5"))
        assert result == RiskLevel.CRITICAL

    def test_deviation_5_0_returns_critical(self, peg_monitor: PegMonitor) -> None:
        result = peg_monitor.classify_risk(Decimal("5.0"))
        assert result == RiskLevel.CRITICAL

    def test_uses_decimal_comparison(self, peg_monitor: PegMonitor) -> None:
        """Decimal 型で比較されていること（float を渡さない）。"""
        result = peg_monitor.classify_risk(Decimal("0.499999"))
        assert result == RiskLevel.LOW


class TestGetPegStatus:
    @pytest.mark.asyncio
    async def test_get_peg_status_returns_peg_status(self, peg_monitor: PegMonitor) -> None:
        result = await peg_monitor.get_peg_status()
        assert isinstance(result, PegStatus)

    @pytest.mark.asyncio
    async def test_get_peg_status_ratio_is_decimal(self, peg_monitor: PegMonitor) -> None:
        result = await peg_monitor.get_peg_status()
        assert isinstance(result.current_ratio, Decimal)

    @pytest.mark.asyncio
    async def test_get_peg_status_deviation_is_decimal(self, peg_monitor: PegMonitor) -> None:
        result = await peg_monitor.get_peg_status()
        assert isinstance(result.deviation_pct, Decimal)

    @pytest.mark.asyncio
    async def test_get_peg_status_normal_ratio_low_risk(self, peg_monitor: PegMonitor) -> None:
        """比率 1.0 のとき LOW リスクを返す。"""
        result = await peg_monitor.get_peg_status()
        assert result.risk_level == RiskLevel.LOW


class TestShouldTriggerEvacuation:
    @pytest.mark.asyncio
    async def test_normal_peg_no_evacuation(self, peg_monitor: PegMonitor) -> None:
        result = await peg_monitor.should_trigger_evacuation()
        assert result is False

    @pytest.mark.asyncio
    async def test_critical_deviation_triggers_evacuation(
        self, mock_lido_client: AsyncMock
    ) -> None:
        """乖離 3% のとき避難をトリガーする。"""
        mock_lido_client.get_steth_eth_ratio.return_value = Decimal("0.97")
        monitor = PegMonitor(lido_client=mock_lido_client)
        result = await monitor.should_trigger_evacuation()
        assert result is True
