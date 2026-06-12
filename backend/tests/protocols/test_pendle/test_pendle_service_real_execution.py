# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle サービス層の実行パステスト（non-dry_run）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.protocols.pendle.client import PendleRouterV4Client
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


_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
_MARKET = "0x" + "aa" * 20
_TOKEN_IN = "0x" + "bb" * 20  # noqa: S106 — トークンアドレス（パスワードではない）
_RECEIVER = "0x" + "dd" * 20


def _sdk_resp(
    *,
    to: str = _ROUTER,
    data: str = "0xdeadbeef",
    approvals: list | None = None,
) -> dict:
    """テスト用 SDK レスポンスを生成する。"""
    resp: dict = {
        "data": {
            "tx": {"to": to, "data": data},
            "amountOut": str(int(Decimal("0.95") * Decimal(10**18))),
        }
    }
    if approvals is not None:
        resp["data"]["approvals"] = approvals
    return resp


@pytest.fixture
def router_client_write_enabled() -> PendleRouterV4Client:
    """enable_onchain_write=True の RouterV4 クライアント（実コードパス統合テスト用）。

    Q1 ガード（enable_onchain_write=False）は test_pendle_router_v4_guard.py で検証済み。
    本クラスは Q1 をバイパスし、_extract_approvals / _verify_router の実コードパスをテストする。
    """
    config = PendleConfig(sandbox=False)
    config.enable_onchain_write = True
    return PendleRouterV4Client(config)


class TestRouterV4RealCalldataPath:
    """PendleRouterV4Client の実コードパス統合テスト。

    test_pendle_router_v4_guard.py / test_pendle_router_v4_security.py との重複を避け、
    カバレッジ計測で未到達だった _extract_approvals 内の非 dict スキップ分岐を通す。
    """

    @pytest.mark.asyncio
    async def test_extract_approvals_skips_non_dict_items(
        self, router_client_write_enabled: PendleRouterV4Client
    ) -> None:
        """_extract_approvals が非 dict 要素（文字列・None）を無視して dict のみを返すこと。

        approvals リストに dict と非 dict が混在する場合、非 dict は continue でスキップされ、
        有効な dict アイテムのみが RouterV4Approval として返される。
        """
        # 非 dict 要素（文字列、None）を混在させた approvals を _call_sdk がモックで返す
        mixed_approvals = [
            "invalid_string_item",  # 非 dict — continue 分岐を通す
            None,  # 非 dict — continue 分岐を通す
            {"token": _TOKEN_IN, "spender": _ROUTER, "amount": "100"},  # 有効な dict
        ]
        sdk_resp = _sdk_resp(approvals=mixed_approvals)

        with patch.object(
            router_client_write_enabled,
            "_call_sdk",
            new=AsyncMock(return_value=sdk_resp),
        ):
            result = await router_client_write_enabled.buy_yt(
                _MARKET,
                _TOKEN_IN,
                Decimal("1.0"),
                _RECEIVER,
            )

        # 非 dict をスキップして dict のみが approvals に残ること
        assert result.success is True
        assert len(result.approvals) == 1
        assert result.approvals[0].spender == _ROUTER
        assert result.approvals[0].token == _TOKEN_IN

    @pytest.mark.asyncio
    async def test_extract_approvals_all_non_dict_returns_empty(
        self, router_client_write_enabled: PendleRouterV4Client
    ) -> None:
        """approvals が全て非 dict のとき空リストが返り、Router 照合が通過すること。"""
        all_invalid_approvals: list = ["str_item", 42, None]
        sdk_resp = _sdk_resp(approvals=all_invalid_approvals)

        with patch.object(
            router_client_write_enabled,
            "_call_sdk",
            new=AsyncMock(return_value=sdk_resp),
        ):
            result = await router_client_write_enabled.buy_yt(
                _MARKET,
                _TOKEN_IN,
                Decimal("1.0"),
                _RECEIVER,
            )

        # 非 dict を全てスキップした結果、approvals は空 → Router 照合は通過し success=True
        assert result.success is True
        assert result.approvals == []
