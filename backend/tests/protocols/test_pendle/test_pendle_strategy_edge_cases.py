# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle 戦略のエッジケース・実行パステスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.protocols.pendle.schemas import PendleMarketInfo
from app.protocols.pendle.strategy import (
    LidoPendleCompoundStrategy,
    PendleFixedYieldStrategy,
    PendleYieldLeverageStrategy,
)


def _make_market_info(
    days: int = 30, pt_price: str = "0.95", yt_price: str = "0.05"
) -> PendleMarketInfo:
    return PendleMarketInfo(
        market_address="0x" + "0" * 40,
        underlying_asset="stETH",
        maturity=datetime.now(timezone.utc) + timedelta(days=days),
        days_to_maturity=days,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal(pt_price),
        yt_price=Decimal(yt_price),
        tvl_usd=Decimal("50000000"),
    )


class TestFixedYieldStrategyEdgeCases:
    """PendleFixedYieldStrategy エッジケース。"""

    @pytest.mark.asyncio
    async def test_zero_days_returns_zero_apy(self) -> None:
        """days_to_maturity = 0 のとき expected_apy = 0 で非推奨。"""
        strategy = PendleFixedYieldStrategy()
        market_info = _make_market_info(days=0)
        result = await strategy.evaluate(market_info, Decimal("1.5"))

        assert result.recommended is False
        assert result.expected_apy == Decimal("0")
        assert result.strategy == "pt_fixed"

    @pytest.mark.asyncio
    async def test_zero_pt_price_returns_zero_apy(self) -> None:
        """pt_price = 0 のとき expected_apy = 0 で非推奨。"""
        strategy = PendleFixedYieldStrategy()
        market_info = _make_market_info(pt_price="0", yt_price="0")
        result = await strategy.evaluate(market_info, Decimal("1.5"))

        assert result.recommended is False
        assert result.expected_apy == Decimal("0")


class TestYieldLeverageStrategyEdgeCases:
    """PendleYieldLeverageStrategy エッジケース。"""

    @pytest.mark.asyncio
    async def test_zero_days_returns_zero_apy(self) -> None:
        """days_to_maturity = 0 のとき expected_apy = 0 で非推奨。"""
        strategy = PendleYieldLeverageStrategy()
        market_info = _make_market_info(days=0)
        result = await strategy.evaluate(market_info, Decimal("3.5"))

        assert result.recommended is False
        assert result.expected_apy == Decimal("0")
        assert result.strategy == "yt_leverage"

    @pytest.mark.asyncio
    async def test_zero_yt_price_returns_zero_apy(self) -> None:
        """yt_price = 0 のとき expected_apy = 0 で非推奨。"""
        strategy = PendleYieldLeverageStrategy()
        market_info = _make_market_info(pt_price="1.0", yt_price="0")
        result = await strategy.evaluate(market_info, Decimal("3.5"))

        assert result.recommended is False
        assert result.expected_apy == Decimal("0")

    @pytest.mark.asyncio
    async def test_below_breakeven_details_contain_message(self) -> None:
        """ブレークイーブン未達のとき details にその旨が含まれること。"""
        strategy = PendleYieldLeverageStrategy()
        market_info = _make_market_info()
        # very low staking APR → below breakeven
        result = await strategy.evaluate(market_info, Decimal("0.01"))

        assert "ブレークイーブン" in result.details


class TestLidoPendleCompoundStrategyExecute:
    """LidoPendleCompoundStrategy.execute の実行パステスト。"""

    @pytest.fixture
    def mock_lido(self) -> AsyncMock:
        client = AsyncMock()
        client.get_staking_apr.return_value = Decimal("3.5")
        return client

    @pytest.fixture
    def mock_pendle(self) -> AsyncMock:
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

    @pytest.mark.asyncio
    async def test_execute_non_dry_run_pt_fixed(
        self, mock_lido: AsyncMock, mock_pendle: AsyncMock
    ) -> None:
        """dry_run=False の pt_fixed 実行パスが通ること（LidoService を module-level でパッチ）。"""
        from app.protocols.lido.schemas import LidoStakeResponse  # noqa: PLC0415

        mock_stake_response = LidoStakeResponse(
            operation="STAKE",
            amount_eth=Decimal("1.0"),
            received_steth=Decimal("1.0"),
            tx_hash="0x" + "cc" * 32,
            staking_apr=Decimal("3.5"),
            dry_run=False,
        )

        strategy = LidoPendleCompoundStrategy(lido_client=mock_lido, pendle_client=mock_pendle)

        # LidoService はファンクション内ローカルインポートなので lido.service モジュールをパッチ
        with patch("app.protocols.lido.service.LidoService") as mock_lido_svc_cls:
            mock_lido_svc = AsyncMock()
            mock_lido_svc.stake.return_value = mock_stake_response
            mock_lido_svc_cls.return_value = mock_lido_svc

            result = await strategy.execute(
                amount_eth=Decimal("1.0"),
                strategy="pt_fixed",
                dry_run=False,
            )

        assert result.dry_run is False
        assert "PT" in result.final_position
        assert isinstance(result.total_expected_apy, Decimal)
        assert len(result.steps) > 0

    @pytest.mark.asyncio
    async def test_execute_non_dry_run_yt_leverage(
        self, mock_lido: AsyncMock, mock_pendle: AsyncMock
    ) -> None:
        """dry_run=False の yt_leverage 実行パスが通ること。"""
        from app.protocols.lido.schemas import LidoStakeResponse  # noqa: PLC0415

        mock_stake_response = LidoStakeResponse(
            operation="STAKE",
            amount_eth=Decimal("1.0"),
            received_steth=Decimal("1.0"),
            tx_hash="0x" + "dd" * 32,
            staking_apr=Decimal("3.5"),
            dry_run=False,
        )

        strategy = LidoPendleCompoundStrategy(lido_client=mock_lido, pendle_client=mock_pendle)

        with patch("app.protocols.lido.service.LidoService") as mock_lido_svc_cls:
            mock_lido_svc = AsyncMock()
            mock_lido_svc.stake.return_value = mock_stake_response
            mock_lido_svc_cls.return_value = mock_lido_svc

            result = await strategy.execute(
                amount_eth=Decimal("1.0"),
                strategy="yt_leverage",
                dry_run=False,
            )

        assert result.dry_run is False
        assert "YT" in result.final_position

    @pytest.mark.asyncio
    async def test_execute_dry_run_fallback_without_lido_config(
        self, mock_lido: AsyncMock, mock_pendle: AsyncMock
    ) -> None:
        """lido_config 取得失敗時でも dry_run=True で動作すること。"""
        strategy = LidoPendleCompoundStrategy(lido_client=mock_lido, pendle_client=mock_pendle)

        # get_lido_config はローカルインポートなので lido.config モジュールレベルでパッチ
        with patch(
            "app.protocols.lido.config.get_lido_config",
            side_effect=Exception("設定なし"),
        ):
            result = await strategy.execute(
                amount_eth=Decimal("1.0"),
                strategy="pt_fixed",
                dry_run=True,
            )

        assert result.dry_run is True
        assert isinstance(result.total_expected_apy, Decimal)

    @pytest.mark.asyncio
    async def test_execute_non_dry_run_without_lido_service_falls_back(
        self, mock_lido: AsyncMock, mock_pendle: AsyncMock
    ) -> None:
        """lido_config 取得失敗時の non-dry_run はフォールバックで動作すること。"""
        strategy = LidoPendleCompoundStrategy(lido_client=mock_lido, pendle_client=mock_pendle)

        with patch(
            "app.protocols.lido.config.get_lido_config",
            side_effect=Exception("設定なし"),
        ):
            result = await strategy.execute(
                amount_eth=Decimal("1.0"),
                strategy="yt_leverage",
                dry_run=False,
            )

        # フォールバック経路でもクラッシュしないこと
        assert isinstance(result.total_expected_apy, Decimal)
