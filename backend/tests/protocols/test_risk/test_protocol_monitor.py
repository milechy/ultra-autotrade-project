"""ProtocolMonitor のユニットテスト。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.aave.client import AccountData
from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.risk.protocol_monitor import ProtocolMonitor
from app.protocols.risk.schemas import ProtocolHealth, RiskLevel


def _build_aave_monitor(
    mock_lido_client: AsyncMock,
    mock_pendle_client: AsyncMock,
    monitoring_service: MagicMock,
    aave_client: Mock,
) -> ProtocolMonitor:
    """Aave 依存を差し替えた ProtocolMonitor を構築するヘルパー。"""
    return ProtocolMonitor(
        lido_client=mock_lido_client,
        pendle_client=mock_pendle_client,
        monitoring_service=monitoring_service,
        aave_client=aave_client,
    )


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

    @pytest.mark.asyncio
    async def test_aave_health_no_alerts_when_healthy(
        self, protocol_monitor: ProtocolMonitor
    ) -> None:
        """HF=2.5（健全）のときアラートなし。"""
        result = await protocol_monitor.check_aave_health()
        assert result.alerts == []

    @pytest.mark.asyncio
    async def test_aave_health_tvl_equals_total_collateral_usd(
        self, protocol_monitor: ProtocolMonitor, mock_aave_client: Mock
    ) -> None:
        """tvl_usd は AccountData.total_collateral_usd（担保 USD）と一致し Decimal 型。"""
        result = await protocol_monitor.check_aave_health()
        expected = mock_aave_client.get_account_data.return_value.total_collateral_usd
        assert result.tvl_usd == expected
        assert isinstance(result.tvl_usd, Decimal)

    @pytest.mark.asyncio
    async def test_aave_health_high_risk_hf_below_warning(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """HF=1.7（警告水準 1.8 未満）のとき HIGH リスク + アラート。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = Decimal("1.7")
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.HIGH
        assert len(result.alerts) == 1
        assert "警告水準" in result.alerts[0]

    @pytest.mark.asyncio
    async def test_aave_health_critical_hf_below_hard_stop(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """HF=1.5（緊急停止水準 1.6 未満）のとき CRITICAL リスク + アラート。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = Decimal("1.5")
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.CRITICAL
        assert len(result.alerts) == 1
        assert "緊急停止水準" in result.alerts[0]

    @pytest.mark.asyncio
    async def test_aave_health_boundary_hf_exactly_1_6_is_high(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """HF=1.6 ちょうど（< 1.6 ではない）のとき CRITICAL ではなく HIGH。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = Decimal("1.6")
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.HIGH
        assert len(result.alerts) == 1
        assert "警告水準" in result.alerts[0]

    @pytest.mark.asyncio
    async def test_aave_health_boundary_hf_exactly_1_8_is_low(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """HF=1.8 ちょうど（< 1.8 ではない）のとき HIGH ではなく LOW + アラートなし。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = Decimal("1.8")
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.LOW
        assert result.alerts == []

    @pytest.mark.asyncio
    async def test_aave_health_low_risk_hf_none_and_inf(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """monitoring HF=None + account HF=inf（ポジションなし）のとき LOW リスク。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = None
        mock_aave_client.get_account_data.return_value = AccountData(
            total_collateral_usd=Decimal("0"),
            total_debt_usd=Decimal("0"),
            available_borrows_usd=Decimal("0"),
            health_factor=Decimal("inf"),
        )
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.LOW
        assert result.alerts == []

    @pytest.mark.asyncio
    async def test_aave_health_hf_fallback_to_account_data(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """monitoring HF=None のとき AccountData.health_factor にフォールバックする。"""
        mock_monitoring_service.get_status.return_value.last_health_factor = None
        mock_aave_client.get_account_data.return_value = AccountData(
            total_collateral_usd=Decimal("50000"),
            total_debt_usd=Decimal("30000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=Decimal("1.5"),
        )
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_aave_health_fail_open_on_monitoring_error(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """monitoring 例外時は raise せず CRITICAL / is_operational=False を返す。"""
        mock_monitoring_service.get_status.side_effect = RuntimeError(
            "https://rpc.example/v2/secret-api-key"
        )
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.is_operational is False
        assert result.tvl_usd == Decimal("0")
        # Security Rule 8: alerts は無認証 API で外部露出されるため固定文言のみ。
        # 例外詳細 (RPC URL / APIキー等) が漏れていないことを検証する。
        assert result.alerts == ["Aave ヘルスチェックエラー（詳細はログ参照）"]
        assert "secret-api-key" not in result.alerts[0]

    @pytest.mark.asyncio
    async def test_aave_health_fail_open_on_aave_client_error(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """Aave クライアント例外時も fail-open（raise しない）。"""
        mock_aave_client.get_account_data.side_effect = RuntimeError("rpc down")
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.is_operational is False

    @pytest.mark.asyncio
    async def test_aave_health_not_operational_on_emergency_stop(
        self,
        mock_lido_client: AsyncMock,
        mock_pendle_client: AsyncMock,
        mock_monitoring_service: MagicMock,
        mock_aave_client: Mock,
    ) -> None:
        """緊急停止中（is_trading_allowed=False）のとき is_operational=False。"""
        mock_monitoring_service.is_trading_allowed.return_value = False
        monitor = _build_aave_monitor(
            mock_lido_client, mock_pendle_client, mock_monitoring_service, mock_aave_client
        )
        result = await monitor.check_aave_health()
        assert result.is_operational is False

    def test_protocol_monitor_no_args_backward_compat(self) -> None:
        """引数なし ProtocolMonitor() が従来通り構築できる（compound_risk.py / router.py 互換）。"""
        monitor = ProtocolMonitor()
        assert monitor is not None


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
