"""Pendle Finance サービス層のビジネスロジックテスト。"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.client import DummyPendleClient
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import PendleMarketInfo, PendleMintRequest, PendleRedeemRequest
from app.protocols.pendle.service import PendleService


@pytest.fixture
def config() -> PendleConfig:
    return PendleConfig(sandbox=True, min_days_to_maturity=7)


@pytest.fixture
def dummy_client(config: PendleConfig) -> DummyPendleClient:
    return DummyPendleClient(config)


@pytest.fixture
def service(dummy_client: DummyPendleClient, config: PendleConfig) -> PendleService:
    return PendleService(client=dummy_client, config=config)


class TestPendleServiceMintDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_default_true(self, service: PendleService) -> None:
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
        )
        assert req.dry_run is True
        response = await service.mint(req)
        assert response.dry_run is True
        assert response.tx_hash is None

    @pytest.mark.asyncio
    async def test_dry_run_returns_simulated_response(self, service: PendleService) -> None:
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        assert response.operation == "MINT_PT"
        assert response.input_amount == Decimal("1.0")
        assert response.pt_received is not None
        assert response.yt_received is None

    @pytest.mark.asyncio
    async def test_yt_leverage_dry_run(self, service: PendleService) -> None:
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="yt_leverage",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        assert response.operation == "MINT_YT"
        assert response.yt_received is not None
        assert response.pt_received is None


class TestPendleServiceMaturityCheck:
    @pytest.mark.asyncio
    async def test_maturity_less_than_min_raises_error(self, config: PendleConfig) -> None:
        """満期まで 7 日未満の場合は ValueError を発生させる。"""
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        mock_client = AsyncMock()
        from app.protocols.pendle.schemas import PendleMarketInfo  # noqa: PLC0415

        mock_client.get_market_info.return_value = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=datetime.now(tz=timezone.utc) + timedelta(days=3),
            days_to_maturity=3,  # min=7 未満
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
        )

        with pytest.raises(ValueError, match="満期まで"):
            await svc.mint(req)

    @pytest.mark.asyncio
    async def test_maturity_exactly_at_min_is_allowed(self, config: PendleConfig) -> None:
        """満期まで min_days_to_maturity 日ちょうどは許可される。"""
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        mock_client = AsyncMock()
        from app.protocols.pendle.schemas import PendleMarketInfo  # noqa: PLC0415

        mock_client.get_market_info.return_value = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=datetime.now(tz=timezone.utc) + timedelta(days=7),
            days_to_maturity=7,  # ちょうど min
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
        )
        response = await svc.mint(req)
        assert response is not None


class TestPendleServiceApyWarning:
    @pytest.mark.asyncio
    async def test_high_implied_apy_logs_warning(
        self, config: PendleConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        """implied APY > 100% で WARNING ログが出ることを確認。"""
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        mock_client = AsyncMock()
        from app.protocols.pendle.schemas import PendleMarketInfo  # noqa: PLC0415

        mock_client.get_market_info.return_value = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=datetime.now(tz=timezone.utc) + timedelta(days=30),
            days_to_maturity=30,
            implied_apy=Decimal("150.0"),  # 100% 超え
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
        )

        with caplog.at_level(logging.WARNING, logger="app.protocols.pendle.service"):
            await svc.mint(req)

        assert any("implied APY 警告" in record.message for record in caplog.records)


class TestPendleServicePtFixedCalculation:
    @pytest.mark.asyncio
    async def test_pt_fixed_amount_calculation(self, service: PendleService) -> None:
        """pt_fixed 戦略: pt_received = amount / pt_price (0.95)"""
        amount = Decimal("1.0")
        req = PendleMintRequest(
            asset="stETH",
            amount=amount,
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        expected_pt = amount / Decimal("0.95")
        assert response.pt_received == expected_pt

    @pytest.mark.asyncio
    async def test_yt_leverage_amount_calculation(self, service: PendleService) -> None:
        """yt_leverage 戦略: yt_received = amount / yt_price (0.05)"""
        amount = Decimal("1.0")
        req = PendleMintRequest(
            asset="stETH",
            amount=amount,
            strategy="yt_leverage",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        expected_yt = amount / Decimal("0.05")
        assert response.yt_received == expected_yt

    @pytest.mark.asyncio
    async def test_implied_fixed_yield_calculation(self, service: PendleService) -> None:
        """implied_fixed_yield = (1 - pt_price) / pt_price * (365 / days) * 100"""
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        # pt_price=0.95, days=30
        expected = (
            (Decimal("1") - Decimal("0.95"))
            / Decimal("0.95")
            * (Decimal("365") / Decimal("30"))
            * Decimal("100")
        )
        assert response.implied_fixed_yield == expected


class TestPendleServiceEstimateFixedYield:
    @pytest.mark.asyncio
    async def test_estimate_fixed_yield_returns_decimal(self, service: PendleService) -> None:
        result = await service.estimate_fixed_yield(Decimal("1.0"), "0x" + "0" * 40)
        assert type(result) is Decimal

    @pytest.mark.asyncio
    async def test_estimate_fixed_yield_correct_calculation(self, service: PendleService) -> None:
        """pt_price=0.95, days=30 の場合の年換算利回りを確認。"""
        result = await service.estimate_fixed_yield(Decimal("1.0"), "0x" + "0" * 40)
        expected = (
            (Decimal("1") - Decimal("0.95"))
            / Decimal("0.95")
            * (Decimal("365") / Decimal("30"))
            * Decimal("100")
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_estimate_fixed_yield_is_positive(self, service: PendleService) -> None:
        result = await service.estimate_fixed_yield(Decimal("1.0"), "0x" + "0" * 40)
        assert result > Decimal("0")


class TestPendleServiceDecimalPrecision:
    @pytest.mark.asyncio
    async def test_all_response_fields_are_decimal(self, service: PendleService) -> None:
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("0.123456789012345678"),
            strategy="pt_fixed",
            market_address="0x" + "0" * 40,
            dry_run=True,
        )
        response = await service.mint(req)
        assert type(response.input_amount) is Decimal
        assert type(response.implied_fixed_yield) is Decimal
        assert response.pt_received is not None
        assert type(response.pt_received) is Decimal


class TestPendleServiceRedeemMaturityCheck:
    def _make_market_info(self, days_to_maturity: int) -> PendleMarketInfo:
        return PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=datetime.now(tz=timezone.utc) + timedelta(days=days_to_maturity),
            days_to_maturity=days_to_maturity,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )

    @pytest.mark.asyncio
    async def test_redeem_pt_blocked_before_maturity(self, config: PendleConfig) -> None:
        """PT リデームは満期前（days_to_maturity=30）にブロックされること。"""
        mock_client = AsyncMock()
        mock_client.get_market_info.return_value = self._make_market_info(30)
        svc = PendleService(client=mock_client, config=config)
        req = PendleRedeemRequest(
            token_type="PT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )

        with pytest.raises(ValueError, match="Cannot redeem PT before maturity"):
            await svc.redeem(req)

    @pytest.mark.asyncio
    async def test_redeem_pt_allowed_at_maturity(self, config: PendleConfig) -> None:
        """PT リデームは満期時（days_to_maturity=0）に成功すること。"""
        mock_client = AsyncMock()
        mock_client.get_market_info.return_value = self._make_market_info(0)
        mock_client.redeem_pt.return_value = {
            "success": True,
            "underlying_received": Decimal("1.0"),
            "tx_hash": "0x" + "cc" * 32,
        }
        svc = PendleService(client=mock_client, config=config)
        req = PendleRedeemRequest(
            token_type="PT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
            dry_run=False,
        )

        response = await svc.redeem(req)
        assert response is not None
        assert response.operation == "REDEEM_PT"

    @pytest.mark.asyncio
    async def test_redeem_yt_not_blocked_by_maturity(self, config: PendleConfig) -> None:
        """YT リデームは満期チェックに影響されないこと（days_to_maturity=30 でも成功）。"""
        mock_client = AsyncMock()
        mock_client.get_market_info.return_value = self._make_market_info(30)
        mock_client.redeem_yt.return_value = {
            "success": True,
            "underlying_received": Decimal("0.05"),
            "tx_hash": "0x" + "dd" * 32,
        }
        svc = PendleService(client=mock_client, config=config)
        req = PendleRedeemRequest(
            token_type="YT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
            dry_run=False,
        )

        response = await svc.redeem(req)
        assert response is not None
        assert response.operation == "REDEEM_YT"
