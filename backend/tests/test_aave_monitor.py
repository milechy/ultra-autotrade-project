# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_monitor.py
"""Tests for app.aave.monitor module."""

import os
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from app.aave.monitor import get_aave_balance, get_health_factor
from app.aave.schemas import AaveBalanceInfo


class TestGetHealthFactor:
    """get_health_factor() のテスト。"""

    def test_returns_none_when_wallet_address_not_set(self) -> None:
        """AAVE_WALLET_ADDRESS 未設定時は None を返す。"""
        env: dict[str, str] = {}
        with patch.dict(os.environ, env):
            os.environ.pop("AAVE_WALLET_ADDRESS", None)
            result = get_health_factor()
        assert result is None

    def test_dummy_client_returns_safe_value(self) -> None:
        """AAVE_CLIENT_TYPE=dummy の場合は DummyAaveClient の値 2.5 を返す。"""
        with patch.dict(
            os.environ,
            {"AAVE_CLIENT_TYPE": "dummy", "AAVE_WALLET_ADDRESS": "0x" + "a" * 40},
        ):
            result = get_health_factor()
        assert result == Decimal("2.5")

    def test_explicit_wallet_address_overrides_env(self) -> None:
        """引数で wallet_address を渡した場合は env var より優先する。"""
        with patch.dict(os.environ, {"AAVE_CLIENT_TYPE": "dummy"}):
            result = get_health_factor(wallet_address="0x" + "b" * 40)
        assert result == Decimal("2.5")

    def test_web3_returns_none_when_rpc_url_not_set(self) -> None:
        """AAVE_CLIENT_TYPE=web3 かつ AAVE_RPC_URL 未設定時は None を返す。"""
        env = {"AAVE_CLIENT_TYPE": "web3", "AAVE_WALLET_ADDRESS": "0x" + "a" * 40}
        with patch.dict(os.environ, env):
            os.environ.pop("AAVE_RPC_URL", None)
            os.environ.pop("AAVE_POOL_ADDRESS", None)
            result = get_health_factor()
        assert result is None

    def test_web3_returns_none_when_pool_address_not_set(self) -> None:
        """AAVE_CLIENT_TYPE=web3 かつ AAVE_POOL_ADDRESS 未設定時は None を返す。"""
        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
        }
        with patch.dict(os.environ, env):
            os.environ.pop("AAVE_POOL_ADDRESS", None)
            result = get_health_factor()
        assert result is None

    def test_web3_returns_hf_from_mock_client(self) -> None:
        """AAVE_CLIENT_TYPE=web3 の場合は Web3AaveClient.get_health_factor() の値を返す。"""
        mock_client: Any = MagicMock()
        mock_client.get_health_factor.return_value = Decimal("1.95")

        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_POOL_ADDRESS": "0x" + "b" * 40,
        }
        with (
            patch.dict(os.environ, env),
            patch("app.aave.client.Web3AaveClient", return_value=mock_client),
        ):
            result = get_health_factor()

        assert result == Decimal("1.95")
        mock_client.get_health_factor.assert_called_once_with("0x" + "a" * 40)

    def test_web3_returns_none_on_exception(self) -> None:
        """Web3AaveClient が例外を投げた場合は None を返す（fail-open）。"""
        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_POOL_ADDRESS": "0x" + "b" * 40,
        }
        with (
            patch.dict(os.environ, env),
            patch("app.aave.client.Web3AaveClient", side_effect=RuntimeError("RPC error")),
        ):
            result = get_health_factor()

        assert result is None

    def test_unknown_client_type_returns_none(self) -> None:
        """不明な AAVE_CLIENT_TYPE の場合は None を返す。"""
        with patch.dict(
            os.environ,
            {"AAVE_CLIENT_TYPE": "unknown", "AAVE_WALLET_ADDRESS": "0x" + "a" * 40},
        ):
            result = get_health_factor()
        assert result is None

    def test_infinity_hf_returns_none(self) -> None:
        """Decimal('Infinity')（ポジションなし）は None に正規化される。"""
        mock_client: Any = MagicMock()
        mock_client.get_health_factor.return_value = Decimal("Infinity")

        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_POOL_ADDRESS": "0x" + "b" * 40,
        }
        with (
            patch.dict(os.environ, env),
            patch("app.aave.client.Web3AaveClient", return_value=mock_client),
        ):
            result = get_health_factor()

        assert result is None

    def test_dummy_infinity_returns_none(self) -> None:
        """DummyAaveClient が Infinity を返した場合も None に正規化される。"""
        mock_dummy: Any = MagicMock()
        mock_dummy.get_health_factor.return_value = Decimal("Infinity")

        with (
            patch.dict(
                os.environ,
                {"AAVE_CLIENT_TYPE": "dummy", "AAVE_WALLET_ADDRESS": "0x" + "a" * 40},
            ),
            patch("app.aave.client.DummyAaveClient", return_value=mock_dummy),
        ):
            result = get_health_factor()

        assert result is None


class TestGetAaveBalance:
    """get_aave_balance() のテスト。"""

    def test_dummy_returns_mock_values(self) -> None:
        """AAVE_CLIENT_TYPE=dummy の場合はモック残高を返す。"""
        with patch.dict(
            os.environ,
            {"AAVE_CLIENT_TYPE": "dummy", "AAVE_WALLET_ADDRESS": "0x" + "a" * 40},
        ):
            balance = get_aave_balance()

        assert isinstance(balance, AaveBalanceInfo)
        assert balance.usdc_balance == Decimal("1000")
        assert balance.a_usdc_balance == Decimal("500")

    def test_no_wallet_address_returns_mock(self) -> None:
        """AAVE_WALLET_ADDRESS 未設定時はモック残高を返す。"""
        with patch.dict(os.environ, {"AAVE_CLIENT_TYPE": "web3"}):
            os.environ.pop("AAVE_WALLET_ADDRESS", None)
            balance = get_aave_balance()

        assert balance.usdc_balance == Decimal("1000")

    def test_web3_returns_balance_from_rpc(self) -> None:
        """AAVE_CLIENT_TYPE=web3 の場合は ERC-20 balanceOf から残高を取得する。"""
        mock_contract: Any = MagicMock()
        mock_contract.functions.decimals.return_value.call.return_value = 6
        mock_contract.functions.balanceOf.return_value.call.return_value = 500_000_000  # 500 USDC

        mock_w3: Any = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract

        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_USDC_ADDRESS": "0x" + "c" * 40,
        }
        with patch.dict(os.environ, env), patch("web3.Web3", return_value=mock_w3):
            os.environ.pop("AAVE_A_USDC_ADDRESS", None)
            balance = get_aave_balance()

        assert balance.usdc_balance == Decimal("500")
        assert balance.a_usdc_balance == Decimal("0")

    def test_web3_balance_fetch_failure_returns_zero(self) -> None:
        """ERC-20 呼び出しが失敗した場合は残高 0 を返す（fail-safe）。"""
        env = {
            "AAVE_CLIENT_TYPE": "web3",
            "AAVE_WALLET_ADDRESS": "0x" + "a" * 40,
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_USDC_ADDRESS": "0x" + "c" * 40,
        }
        with (
            patch.dict(os.environ, env),
            patch("web3.Web3", side_effect=RuntimeError("connection error")),
        ):
            balance = get_aave_balance()

        assert balance.usdc_balance == Decimal("0")