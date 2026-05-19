# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle サービス層の実行パステスト（non-dry_run）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import (
    PendleMarketInfo,
    PendleMintRequest,
    PendleRedeemRequest,
)
from app.protocols.pendle.service import PendleService

_MARKET_ADDR = "0x" + "0" * 40


def _make_market_info(days: int = 30) -> PendleMarketInfo:
    return PendleMarketInfo(
        market_address=_MARKET_ADDR,
        underlying_asset="stETH",
        maturity=datetime.now(timezone.utc) + timedelta(days=days),
        days_to_maturity=days,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal("0.95"),
        yt_price=Decimal("0.05"),
        tvl_usd=Decimal("50000000"),
    )


@pytest.fixture
def config() -> PendleConfig:
    return PendleConfig(sandbox=True, min_days_to_maturity=7)


@pytest.fixture
def mock_client() -> AsyncMock:
    """正常動作するモック Pendle クライアント。"""
    client = AsyncMock()
    client.get_market_info.return_value = _make_market_info()
    client.mint_sy.return_value = {
        "success": True,
        "sy_received": Decimal("1.0"),
        "tx_hash": "0x" + "aa" * 32,
    }
    client.mint_pt_yt.return_value = {
        "success": True,
        "pt_received": Decimal("1.052631"),
        "yt_received": Decimal("20.0"),
        "tx_hash": "0x" + "bb" * 32,
    }
    return client


class TestMintRealExecution:
    """dry_run=False のミント実行パスのテスト。"""

    @pytest.mark.asyncio
    async def test_mint_pt_fixed_real_execution(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """dry_run=False で PT ミントが実行されること。"""
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        response = await svc.mint(req)

        assert response.dry_run is False
        assert response.operation == "MINT_PT"
        assert response.tx_hash is not None
        mock_client.mint_sy.assert_awaited_once()
        mock_client.mint_pt_yt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mint_yt_leverage_real_execution(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """dry_run=False で YT ミントが実行されること。"""
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="yt_leverage",
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        response = await svc.mint(req)

        assert response.dry_run is False
        assert response.operation == "MINT_YT"
        assert response.tx_hash is not None
        assert response.yt_received is not None

    @pytest.mark.asyncio
    async def test_mint_sy_failure_raises_runtime_error(self, config: PendleConfig) -> None:
        """SY ミント失敗時に RuntimeError を発生させること。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info()
        client.mint_sy.return_value = {"success": False}

        svc = PendleService(client=client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        with pytest.raises(RuntimeError, match="SY ミント失敗"):
            await svc.mint(req)

    @pytest.mark.asyncio
    async def test_mint_pt_yt_failure_raises_runtime_error(self, config: PendleConfig) -> None:
        """PT/YT 分割失敗時に RuntimeError を発生させること。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info()
        client.mint_sy.return_value = {
            "success": True,
            "sy_received": Decimal("1.0"),
        }
        client.mint_pt_yt.return_value = {"success": False}

        svc = PendleService(client=client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="yt_leverage",
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        with pytest.raises(RuntimeError, match="PT/YT 分割失敗"):
            await svc.mint(req)

    @pytest.mark.asyncio
    async def test_mint_pt_real_amount_is_decimal(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """実行結果の pt_received が Decimal であること。"""
        svc = PendleService(client=mock_client, config=config)
        req = PendleMintRequest(
            asset="stETH",
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        response = await svc.mint(req)

        assert isinstance(response.pt_received, Decimal)
        assert isinstance(response.implied_fixed_yield, Decimal)


class TestRedeemRealExecution:
    """dry_run=False のリデーム実行パスのテスト。"""

    @pytest.mark.asyncio
    async def test_redeem_yt_dry_run_returns_response(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """YT dry_run リデームでレスポンスが返ること。"""
        svc = PendleService(client=mock_client, config=config)
        req = PendleRedeemRequest(
            token_type="YT",
            amount=Decimal("10.0"),
            market_address=_MARKET_ADDR,
            dry_run=True,
        )

        response = await svc.redeem(req)

        assert response.dry_run is True
        assert response.operation == "REDEEM_YT"
        assert response.redeemed_amount == Decimal("10.0")
        assert isinstance(response.underlying_received, Decimal)

    @pytest.mark.asyncio
    async def test_redeem_pt_before_maturity_raises_value_error(self, config: PendleConfig) -> None:
        """満期前の PT リデームは ValueError を発生させること。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info(days=5)  # 5日後 = 満期前

        svc = PendleService(client=client, config=config)
        req = PendleRedeemRequest(
            token_type="PT",
            amount=Decimal("1.0"),
            market_address=_MARKET_ADDR,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="Cannot redeem PT before maturity"):
            await svc.redeem(req)

    @pytest.mark.asyncio
    async def test_redeem_yt_real_execution(self, config: PendleConfig) -> None:
        """dry_run=False で YT リデームが実行されること。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info()
        client.redeem_yt.return_value = {
            "success": True,
            "underlying_received": Decimal("0.5"),
            "tx_hash": "0x" + "ee" * 32,
        }

        svc = PendleService(client=client, config=config)
        req = PendleRedeemRequest(
            token_type="YT",
            amount=Decimal("10.0"),
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        response = await svc.redeem(req)

        assert response.dry_run is False
        assert response.operation == "REDEEM_YT"
        assert response.tx_hash is not None
        client.redeem_yt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redeem_failure_raises_runtime_error(self, config: PendleConfig) -> None:
        """リデーム失敗時に RuntimeError を発生させること。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info()
        client.redeem_yt.return_value = {"success": False}

        svc = PendleService(client=client, config=config)
        req = PendleRedeemRequest(
            token_type="YT",
            amount=Decimal("10.0"),
            market_address=_MARKET_ADDR,
            dry_run=False,
        )

        with pytest.raises(RuntimeError, match="REDEEM_YT 失敗"):
            await svc.redeem(req)


class TestGetMarketInfo:
    """get_market_info メソッドのテスト。"""

    @pytest.mark.asyncio
    async def test_get_market_info_delegates_to_client(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """get_market_info がクライアントに委譲すること。"""
        svc = PendleService(client=mock_client, config=config)
        result = await svc.get_market_info(_MARKET_ADDR)

        assert result is not None
        mock_client.get_market_info.assert_awaited_once_with(_MARKET_ADDR)

    @pytest.mark.asyncio
    async def test_estimate_fixed_yield_returns_decimal(
        self, mock_client: AsyncMock, config: PendleConfig
    ) -> None:
        """estimate_fixed_yield が Decimal を返すこと。"""
        svc = PendleService(client=mock_client, config=config)
        result = await svc.estimate_fixed_yield(Decimal("1.0"), _MARKET_ADDR)

        assert isinstance(result, Decimal)
        assert result > Decimal("0")

    @pytest.mark.asyncio
    async def test_estimate_fixed_yield_zero_days_returns_zero(self, config: PendleConfig) -> None:
        """満期 0 日のとき estimate_fixed_yield は 0 を返すこと。"""
        client = AsyncMock()
        client.get_market_info.return_value = _make_market_info(days=0)

        svc = PendleService(client=client, config=config)
        result = await svc.estimate_fixed_yield(Decimal("1.0"), _MARKET_ADDR)

        assert result == Decimal("0")
