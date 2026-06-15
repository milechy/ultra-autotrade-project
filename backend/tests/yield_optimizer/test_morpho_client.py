# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/yield_optimizer/test_morpho_client.py
"""
MorphoClient のユニットテスト。

外部 Privy API 呼び出しは全て MagicMock / httpx モックで差し替える。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.yield_optimizer.morpho_client import MorphoClient
from app.yield_optimizer.schemas import TxResult

# ------------------------------------------------------------------ helpers


def _make_client(
    app_id: str = "test-app",
    app_secret: str = "test-secret",
    wallet_id: str = "wallet-123",
) -> MorphoClient:
    """テスト用 MorphoClient を生成する。"""
    return MorphoClient(app_id=app_id, app_secret=app_secret, wallet_id=wallet_id)


# ------------------------------------------------------------------ list_vaults


class TestListVaults:
    def test_returns_vault_list_on_success(self) -> None:
        """正常レスポンスから MorphoVault リストをパースできる。"""
        client = _make_client()

        mock_response_data = {
            "vaults": [
                {
                    "vault_address": "0xabc123",
                    "name": "USDC Vault A",
                    "apy": "0.0523",
                    "tvl_usd": "1000000",
                },
                {
                    "vault_address": "0xdef456",
                    "name": "USDC Vault B",
                    "apy": "0.0312",
                    "tvl_usd": "500000",
                },
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp
            mock_client_cls.return_value = mock_ctx

            result = client.list_vaults()

        assert len(result) == 2
        assert result[0].vault_address == "0xabc123"
        assert result[0].name == "USDC Vault A"
        assert Decimal(result[0].apy) == Decimal("0.0523")
        assert result[1].vault_address == "0xdef456"

    def test_returns_empty_list_on_api_failure(self) -> None:
        """Privy API 失敗時は空リストを返す (fail-open)。"""
        client = _make_client()

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = ConnectionError("Network error")
            mock_client_cls.return_value = mock_ctx

            result = client.list_vaults()

        assert result == []

    def test_returns_empty_list_when_credentials_missing(self) -> None:
        """認証情報未設定時は空リストを返す (fail-open)。"""
        client = MorphoClient(app_id="", app_secret="", wallet_id="wallet-123")
        result = client.list_vaults()
        assert result == []

    def test_best_apy_vault_selection(self) -> None:
        """get_best_apy_vault は最高 APY の Vault を返す。"""
        client = _make_client()

        mock_response_data = {
            "vaults": [
                {
                    "vault_address": "0xaaa",
                    "name": "Low APY Vault",
                    "apy": "0.02",
                    "tvl_usd": "100000",
                },
                {
                    "vault_address": "0xbbb",
                    "name": "High APY Vault",
                    "apy": "0.08",
                    "tvl_usd": "200000",
                },
                {
                    "vault_address": "0xccc",
                    "name": "Mid APY Vault",
                    "apy": "0.05",
                    "tvl_usd": "300000",
                },
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp
            mock_client_cls.return_value = mock_ctx

            best = client.get_best_apy_vault()

        assert best is not None
        assert best.vault_address == "0xbbb"
        assert Decimal(best.apy) == Decimal("0.08")

    def test_best_apy_vault_returns_none_when_no_vaults(self) -> None:
        """Vault が存在しない場合は None を返す。"""
        client = MorphoClient(app_id="", app_secret="", wallet_id="")
        result = client.get_best_apy_vault()
        assert result is None


# ------------------------------------------------------------------ deposit_to_vault


class TestDepositToVault:
    def test_deposit_calls_privy_earn_api(self) -> None:
        """deposit_to_vault は Privy Earn API を呼び出す。"""
        client = _make_client()
        vault_addr = "0xvault123"
        amount = Decimal("500.00")

        mock_response_data = {
            "tx_hash": "0xdeadbeef1234",
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.post.return_value = mock_resp
            mock_client_cls.return_value = mock_ctx

            result = client.deposit_to_vault(vault_address=vault_addr, amount_usdc=amount)

        assert isinstance(result, TxResult)
        assert result.tx_hash == "0xdeadbeef1234"
        assert result.vault_address == vault_addr
        assert result.operation == "deposit"
        assert Decimal(result.amount) == amount

        # Privy Earn API が呼ばれたことを確認
        mock_ctx.post.assert_called_once()
        call_url = mock_ctx.post.call_args[0][0]
        assert "earn/deposit" in call_url

    def test_deposit_raises_on_missing_credentials(self) -> None:
        """認証情報未設定時は RuntimeError を送出する。"""
        client = MorphoClient(app_id="", app_secret="", wallet_id="")
        with pytest.raises(RuntimeError, match="PRIVY_APP_ID"):
            client.deposit_to_vault("0xvault", Decimal("100"))

    def test_deposit_raises_when_no_tx_hash_in_response(self) -> None:
        """Privy が tx_hash を返さない場合は RuntimeError を送出する。"""
        client = _make_client()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # tx_hash なし
        mock_resp.raise_for_status.return_value = None

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.post.return_value = mock_resp
            mock_client_cls.return_value = mock_ctx

            with pytest.raises(RuntimeError, match="no tx_hash"):
                client.deposit_to_vault("0xvault", Decimal("100"))


# ------------------------------------------------------------------ API failure fail-open


class TestApiFailureFailOpen:
    def test_get_all_positions_fail_open(self) -> None:
        """get_all_positions は API 失敗時に空リストを返す (fail-open)。"""
        client = _make_client()

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = Exception("Timeout")
            mock_client_cls.return_value = mock_ctx

            positions = client.get_all_positions()

        assert positions == []

    def test_get_position_fail_open(self) -> None:
        """get_position は API 失敗時に None を返す (fail-open)。"""
        client = _make_client()

        with patch("app.yield_optimizer.morpho_client.httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = Exception("Connection refused")
            mock_client_cls.return_value = mock_ctx

            result = client.get_position("0xvault")

        assert result is None
