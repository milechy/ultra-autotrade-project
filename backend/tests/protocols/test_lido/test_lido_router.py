# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Lido FastAPI ルーターのテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.protocols.lido.router import router
from app.protocols.lido.schemas import (
    LidoAprResponse,
    LidoStakeResponse,
    LidoStatus,
    LidoWithdrawResponse,
)

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _make_lido_status() -> LidoStatus:
    return LidoStatus(
        steth_balance=Decimal("1.5"),
        staking_apr=Decimal("3.5"),
        steth_eth_ratio=Decimal("1.0"),
        peg_deviation_pct=Decimal("0"),
        chain="holesky",
        sandbox=True,
    )


def _make_stake_response(dry_run: bool = True) -> LidoStakeResponse:
    return LidoStakeResponse(
        operation="STAKE",
        amount_eth=Decimal("0.1"),
        received_steth=Decimal("0.1"),
        tx_hash=None if dry_run else "0x" + "ab" * 32,
        staking_apr=Decimal("3.5"),
        dry_run=dry_run,
    )


def _make_withdraw_response(dry_run: bool = True) -> LidoWithdrawResponse:
    return LidoWithdrawResponse(
        operation="WITHDRAW_REQUEST",
        amount_steth=Decimal("0.5"),
        tx_hash=None if dry_run else "0x" + "cd" * 32,
        dry_run=dry_run,
    )


class TestGetLidoStatus:
    """GET /api/protocols/lido/status のテスト。"""

    def test_status_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_status.return_value = _make_lido_status()
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/status")

        assert response.status_code == 200

    def test_status_response_has_steth_balance(self) -> None:
        """レスポンスに steth_balance が含まれること。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_status.return_value = _make_lido_status()
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/status")

        data = response.json()
        assert "steth_balance" in data
        assert "staking_apr" in data
        assert "peg_deviation_pct" in data

    def test_status_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_status.side_effect = RuntimeError("クライアントエラー")
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/status")

        assert response.status_code == 503


class TestStakeEth:
    """POST /api/protocols/lido/stake のテスト。"""

    def test_stake_dry_run_returns_200(self) -> None:
        """dry_run stake で 200 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.stake.return_value = _make_stake_response(dry_run=True)
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/stake",
                json={"amount_eth": "0.1", "dry_run": True},
            )

        assert response.status_code == 200

    def test_stake_response_has_operation_field(self) -> None:
        """レスポンスに operation フィールドが含まれること。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.stake.return_value = _make_stake_response(dry_run=True)
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/stake",
                json={"amount_eth": "0.5", "dry_run": True},
            )

        data = response.json()
        assert data["operation"] == "STAKE"
        assert data["dry_run"] is True

    def test_stake_runtime_error_returns_422(self) -> None:
        """RuntimeError 発生時に 422 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.stake.side_effect = RuntimeError("ペグ乖離エラー")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/stake",
                json={"amount_eth": "0.1", "dry_run": False},
            )

        assert response.status_code == 422

    def test_stake_unexpected_exception_returns_503(self) -> None:
        """予期しない例外発生時に 503 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.stake.side_effect = Exception("予期せぬエラー")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/stake",
                json={"amount_eth": "0.1", "dry_run": True},
            )

        assert response.status_code == 503


class TestWithdrawSteth:
    """POST /api/protocols/lido/withdraw のテスト。"""

    def test_withdraw_dry_run_returns_200(self) -> None:
        """dry_run withdraw で 200 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.withdraw.return_value = _make_withdraw_response(dry_run=True)
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/withdraw",
                json={"amount_steth": "0.5", "dry_run": True},
            )

        assert response.status_code == 200

    def test_withdraw_response_operation(self) -> None:
        """レスポンスに WITHDRAW_REQUEST operation が含まれること。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.withdraw.return_value = _make_withdraw_response(dry_run=True)
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/withdraw",
                json={"amount_steth": "0.5", "dry_run": True},
            )

        data = response.json()
        assert data["operation"] == "WITHDRAW_REQUEST"

    def test_withdraw_runtime_error_returns_422(self) -> None:
        """RuntimeError 発生時に 422 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.withdraw.side_effect = RuntimeError("引き出し失敗")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/withdraw",
                json={"amount_steth": "0.5", "dry_run": False},
            )

        assert response.status_code == 422

    def test_withdraw_unexpected_exception_returns_503(self) -> None:
        """予期しない例外発生時に 503 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.withdraw.side_effect = Exception("ネットワーク障害")
            mock_get_svc.return_value = mock_service

            response = _client.post(
                "/api/protocols/lido/withdraw",
                json={"amount_steth": "0.5", "dry_run": True},
            )

        assert response.status_code == 503


class TestGetLidoApr:
    """GET /api/protocols/lido/apr のテスト。"""

    def test_apr_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_apr.return_value = LidoAprResponse(
                staking_apr=Decimal("3.5"), source="dummy"
            )
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/apr")

        assert response.status_code == 200

    def test_apr_response_has_staking_apr(self) -> None:
        """レスポンスに staking_apr が含まれること。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_apr.return_value = LidoAprResponse(
                staking_apr=Decimal("3.5"), source="dummy"
            )
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/apr")

        data = response.json()
        assert "staking_apr" in data
        assert "source" in data

    def test_apr_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.lido.router._get_service") as mock_get_svc:
            mock_service = AsyncMock()
            mock_service.get_apr.side_effect = Exception("APR 取得失敗")
            mock_get_svc.return_value = mock_service

            response = _client.get("/api/protocols/lido/apr")

        assert response.status_code == 503
