# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rpc_provider.py
"""Tests for RPCProvider failover logic."""

from unittest.mock import MagicMock, patch

import pytest


def _make_w3(connected: bool) -> MagicMock:
    """Helper: create a mock Web3 instance that simulates connected/disconnected."""
    w3 = MagicMock()
    if not connected:
        # _is_connected accesses w3.eth.block_number as a property.
        # Use a property-like side_effect on the eth mock's __getattr__.
        type(w3.eth).block_number = property(
            lambda self: (_ for _ in ()).throw(Exception("connection refused"))
        )
    return w3


class TestRPCProvider:
    """Tests for RPCProvider."""

    def test_primary_connection(self) -> None:
        """プライマリ接続成功時はプライマリのWeb3インスタンスを返す。"""
        mock_w3 = _make_w3(connected=True)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
            MockWeb3.return_value = mock_w3

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc", "https://secondary.rpc")
            result = provider.get_web3()

        assert result is mock_w3
        assert provider._using_secondary is False

    def test_failover_to_secondary(self) -> None:
        """プライマリ失敗時にセカンダリへ切り替わる。"""
        mock_primary = _make_w3(connected=False)
        mock_secondary = _make_w3(connected=True)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
            MockWeb3.side_effect = [mock_primary, mock_secondary]

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc", "https://secondary.rpc")
            result = provider.get_web3()

        assert result is mock_secondary
        assert provider._using_secondary is True

    def test_restore_to_primary(self) -> None:
        """セカンダリ使用中にプライマリが復旧したらプライマリに戻る。"""
        mock_primary_fail = _make_w3(connected=False)
        mock_secondary = _make_w3(connected=True)
        mock_primary_ok = _make_w3(connected=True)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())

            # 1回目の get_web3: プライマリ失敗 → セカンダリ成功
            MockWeb3.side_effect = [mock_primary_fail, mock_secondary]

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc", "https://secondary.rpc")
            provider.get_web3()
            assert provider._using_secondary is True

            # キャッシュをクリアして再試行させる
            provider._current = None

            # 2回目の get_web3: プライマリ復旧
            MockWeb3.side_effect = [mock_primary_ok]
            result = provider.get_web3()

        assert result is mock_primary_ok
        assert provider._using_secondary is False

    def test_both_fail_raises(self) -> None:
        """プライマリ・セカンダリ両方失敗時はConnectionErrorを送出する。"""
        mock_primary = _make_w3(connected=False)
        mock_secondary = _make_w3(connected=False)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
            MockWeb3.side_effect = [mock_primary, mock_secondary]

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc", "https://secondary.rpc")
            with pytest.raises(ConnectionError, match="All RPC endpoints unavailable"):
                provider.get_web3()

    def test_no_secondary_configured(self) -> None:
        """セカンダリ未設定でプライマリ失敗時はConnectionErrorを送出する。"""
        mock_primary = _make_w3(connected=False)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
            MockWeb3.return_value = mock_primary

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc")  # secondary_url=None
            with pytest.raises(ConnectionError, match="All RPC endpoints unavailable"):
                provider.get_web3()

    def test_connection_caching(self) -> None:
        """接続済みインスタンスはキャッシュから返され、Web3コンストラクタは再呼び出しされない。"""
        mock_w3 = _make_w3(connected=True)

        with patch("app.aave.rpc_provider.Web3") as MockWeb3:
            MockWeb3.HTTPProvider = MagicMock(return_value=MagicMock())
            MockWeb3.return_value = mock_w3

            from app.aave.rpc_provider import RPCProvider

            provider = RPCProvider("https://primary.rpc")
            first = provider.get_web3()
            second = provider.get_web3()

        assert first is mock_w3
        assert second is mock_w3
        # Web3コンストラクタは最初の1回のみ呼ばれる
        assert MockWeb3.call_count == 1
