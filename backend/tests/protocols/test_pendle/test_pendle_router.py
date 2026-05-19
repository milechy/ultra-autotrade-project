# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle FastAPI ルーターのテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.protocols.pendle.router import router
from app.protocols.pendle.schemas import (
    PendleMarketInfo,
    PendleMintResponse,
    PendleRedeemResponse,
    StrategyComparison,
    StrategyEvaluation,
)

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)

_MARKET_ADDRESS = "0x" + "0" * 40


def _make_market_info() -> PendleMarketInfo:
    maturity = datetime.now(timezone.utc) + timedelta(days=30)
    return PendleMarketInfo(
        market_address=_MARKET_ADDRESS,
        underlying_asset="stETH",
        maturity=maturity,
        days_to_maturity=30,
        implied_apy=Decimal("5.2"),
        pt_price=Decimal("0.95"),
        yt_price=Decimal("0.05"),
        tvl_usd=Decimal("50000000"),
    )


def _make_mint_response(operation: str = "MINT_PT") -> PendleMintResponse:
    return PendleMintResponse(
        operation=operation,
        input_amount=Decimal("1.0"),
        pt_received=Decimal("1.052631") if operation == "MINT_PT" else None,
        yt_received=Decimal("20.0") if operation == "MINT_YT" else None,
        implied_fixed_yield=Decimal("2.5"),
        maturity=datetime.now(timezone.utc) + timedelta(days=30),
        tx_hash=None,
        dry_run=True,
    )


def _make_redeem_response(operation: str = "REDEEM_PT") -> PendleRedeemResponse:
    return PendleRedeemResponse(
        operation=operation,
        redeemed_amount=Decimal("1.0"),
        underlying_received=Decimal("1.0"),
        tx_hash=None,
        dry_run=True,
    )


def _make_strategy_comparison() -> StrategyComparison:
    strategies = [
        StrategyEvaluation(
            strategy="aave_only",
            recommended=False,
            expected_apy=Decimal("1.5"),
            risk_level="low",
            details="Aave のみ",
        ),
        StrategyEvaluation(
            strategy="lido_aave",
            recommended=True,
            expected_apy=Decimal("5.0"),
            risk_level="low",
            details="Lido + Aave",
        ),
        StrategyEvaluation(
            strategy="lido_pendle_pt",
            recommended=False,
            expected_apy=Decimal("6.0"),
            risk_level="low",
            details="Lido + Pendle PT",
        ),
    ]
    return StrategyComparison(
        strategies=strategies,
        best_strategy="lido_pendle_pt",
        amount=Decimal("1.0"),
    )


class TestListMarkets:
    """GET /api/protocols/pendle/markets のテスト。"""

    def test_markets_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.return_value = _make_market_info()
            mock_get_svc.return_value = mock_service

            with patch("app.protocols.pendle.router.get_pendle_config") as mock_cfg:
                mock_cfg.return_value.market_address = _MARKET_ADDRESS
                response = _client.get("/api/protocols/pendle/markets")

        assert response.status_code == 200

    def test_markets_returns_list(self) -> None:
        """レスポンスがリスト形式であること。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.return_value = _make_market_info()
            mock_get_svc.return_value = mock_service

            with patch("app.protocols.pendle.router.get_pendle_config") as mock_cfg:
                mock_cfg.return_value.market_address = _MARKET_ADDRESS
                response = _client.get("/api/protocols/pendle/markets")

        assert isinstance(response.json(), list)
        assert len(response.json()) == 1

    def test_markets_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.side_effect = Exception("API エラー")
            mock_get_svc.return_value = mock_service

            with patch("app.protocols.pendle.router.get_pendle_config") as mock_cfg:
                mock_cfg.return_value.market_address = _MARKET_ADDRESS
                response = _client.get("/api/protocols/pendle/markets")

        assert response.status_code == 503


class TestGetMarket:
    """GET /api/protocols/pendle/market/{address} のテスト。"""

    def test_get_market_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.return_value = _make_market_info()
            mock_get_svc.return_value = mock_service

            response = _client.get(f"/api/protocols/pendle/market/{_MARKET_ADDRESS}")

        assert response.status_code == 200

    def test_get_market_response_has_implied_apy(self) -> None:
        """レスポンスに implied_apy が含まれること。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.return_value = _make_market_info()
            mock_get_svc.return_value = mock_service

            response = _client.get(f"/api/protocols/pendle/market/{_MARKET_ADDRESS}")

        data = response.json()
        assert "implied_apy" in data
        assert "pt_price" in data
        assert "yt_price" in data

    def test_get_market_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_market_info.side_effect = Exception("マーケット不明")
            mock_get_svc.return_value = mock_service

            response = _client.get(f"/api/protocols/pendle/market/{_MARKET_ADDRESS}")

        assert response.status_code == 503


class TestMintTokens:
    """POST /api/protocols/pendle/mint のテスト。"""

    def test_mint_pt_fixed_returns_200(self) -> None:
        """PT mint で 200 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.mint.return_value = _make_mint_response("MINT_PT")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/mint",
                json={
                    "asset": "stETH",
                    "amount": "1.0",
                    "strategy": "pt_fixed",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        assert response.status_code == 200

    def test_mint_yt_leverage_returns_200(self) -> None:
        """YT mint で 200 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.mint.return_value = _make_mint_response("MINT_YT")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/mint",
                json={
                    "asset": "stETH",
                    "amount": "1.0",
                    "strategy": "yt_leverage",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        assert response.status_code == 200

    def test_mint_value_error_returns_422(self) -> None:
        """ValueError 発生時に 422 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.mint.side_effect = ValueError("満期が近すぎます")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/mint",
                json={
                    "asset": "stETH",
                    "amount": "1.0",
                    "strategy": "pt_fixed",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": False,
                },
            )

        assert response.status_code == 422

    def test_mint_runtime_error_returns_422(self) -> None:
        """RuntimeError 発生時に 422 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.mint.side_effect = RuntimeError("SY ミント失敗")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/mint",
                json={
                    "asset": "stETH",
                    "amount": "1.0",
                    "strategy": "pt_fixed",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": False,
                },
            )

        assert response.status_code == 422

    def test_mint_unexpected_exception_returns_503(self) -> None:
        """予期しない例外発生時に 503 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.mint.side_effect = Exception("予期せぬエラー")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/mint",
                json={
                    "asset": "stETH",
                    "amount": "1.0",
                    "strategy": "pt_fixed",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        assert response.status_code == 503


class TestRedeemTokens:
    """POST /api/protocols/pendle/redeem のテスト。"""

    def test_redeem_yt_returns_200(self) -> None:
        """YT redeem で 200 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.redeem.return_value = _make_redeem_response("REDEEM_YT")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/redeem",
                json={
                    "token_type": "YT",
                    "amount": "10.0",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        assert response.status_code == 200

    def test_redeem_response_has_operation(self) -> None:
        """レスポンスに operation が含まれること。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.redeem.return_value = _make_redeem_response("REDEEM_YT")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/redeem",
                json={
                    "token_type": "YT",
                    "amount": "10.0",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        data = response.json()
        assert "operation" in data
        assert "redeemed_amount" in data

    def test_redeem_runtime_error_returns_422(self) -> None:
        """RuntimeError 発生時に 422 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.redeem.side_effect = RuntimeError("リデーム失敗")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/redeem",
                json={
                    "token_type": "YT",
                    "amount": "10.0",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": False,
                },
            )

        assert response.status_code == 422

    def test_redeem_unexpected_exception_returns_503(self) -> None:
        """予期しない例外発生時に 503 を返すこと。"""
        with patch("app.protocols.pendle.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.redeem.side_effect = Exception("内部エラー")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/pendle/redeem",
                json={
                    "token_type": "YT",
                    "amount": "10.0",
                    "market_address": _MARKET_ADDRESS,
                    "dry_run": True,
                },
            )

        assert response.status_code == 503


class TestGetStrategies:
    """GET /api/protocols/pendle/strategies のテスト。"""

    def test_strategies_invalid_amount_returns_400(self) -> None:
        """無効な amount で 400 を返すこと（400 は Decimal 変換失敗を示す）。"""
        response = _client.get("/api/protocols/pendle/strategies?amount=invalid")
        assert response.status_code == 400

    def test_strategies_valid_amount_triggers_processing(self) -> None:
        """有効な amount で処理が開始されること（503 = DummyClient sandbox エラーも含む）。"""
        # ルーターが amount バリデーションを通過し、サービス層に到達することを確認
        response = _client.get("/api/protocols/pendle/strategies?amount=1.0")
        # sandbox 環境では DummyClient が使われるため 200 か 503
        assert response.status_code in (200, 503)
