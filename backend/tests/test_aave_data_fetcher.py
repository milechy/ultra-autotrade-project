# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Aave マーケットデータ fail-open ヘルパーの単体テスト。"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.aave.client import AaveClientError
from app.automation.aave_data_fetcher import fetch_aave_market_data_safe


def test_aave_data_safe_returns_none_dict_on_full_failure():
    """AaveClient + Liquidity API 両方が失敗した場合、全 None dict を返すこと。"""
    with (
        patch(
            "app.automation.aave_data_fetcher.get_default_aave_client",
            side_effect=AaveClientError("rpc down"),
        ),
        patch(
            "app.automation.aave_data_fetcher._fetch_utilization_async",
            side_effect=Exception("net down"),
        ),
    ):
        result = fetch_aave_market_data_safe()

    assert result == {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }


def test_aave_data_safe_partial_success_health_factor_only():
    """HF 取得成功 + Utilization 失敗時、HF のみ値を持つこと。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("1.85")

    with (
        patch("app.automation.aave_data_fetcher.get_default_aave_client", return_value=mock_client),
        patch(
            "app.automation.aave_data_fetcher._fetch_utilization_async",
            side_effect=Exception("aave api down"),
        ),
    ):
        result = fetch_aave_market_data_safe()

    assert result["health_factor"] == Decimal("1.85")
    assert result["utilization_rate"] is None
    assert result["supply_apy"] is None
    assert result["borrow_apy"] is None


def test_aave_data_safe_inf_health_factor_returns_none():
    """HF=inf (借入なし) の場合、health_factor は None になること。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("inf")

    async def _ok_util(_symbol: str) -> dict:
        return {
            "utilization_rate": Decimal("0.85"),
            "supply_apy": Decimal("0.04"),
            "borrow_apy": Decimal("0.06"),
        }

    with (
        patch("app.automation.aave_data_fetcher.get_default_aave_client", return_value=mock_client),
        patch("app.automation.aave_data_fetcher._fetch_utilization_async", side_effect=_ok_util),
    ):
        result = fetch_aave_market_data_safe()

    assert result["health_factor"] is None
    assert result["utilization_rate"] == Decimal("0.85")
    assert result["supply_apy"] == Decimal("0.04")
    assert result["borrow_apy"] == Decimal("0.06")


def test_aave_data_safe_calls_get_health_factor_no_args():
    """get_health_factor は no-args で呼ばれること (Web3AaveClient は self.account.address を使う)。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.5")

    with (
        patch("app.automation.aave_data_fetcher.get_default_aave_client", return_value=mock_client),
        patch(
            "app.automation.aave_data_fetcher._fetch_utilization_async",
            side_effect=Exception("skip"),
        ),
    ):
        result = fetch_aave_market_data_safe()

    mock_client.get_health_factor.assert_called_once_with()
    assert result["health_factor"] == Decimal("2.5")
