# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Aave マーケットデータ fail-open ヘルパーの単体テスト。

V3 web3 直接呼出 (Pool.getReserveData + ERC20.totalSupply) ベースの実装に対応。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.aave.client import AaveClientError
from app.automation.aave_data_fetcher import (
    _ray_to_apy_pct,
    fetch_aave_market_data_safe,
)


def _make_pool_call_result(
    *,
    liquidity_rate_ray: int = 50_000_000_000_000_000_000_000_000,  # 5% APR
    variable_borrow_rate_ray: int = 80_000_000_000_000_000_000_000_000,  # 8% APR
    atoken_addr: str = "0x0000000000000000000000000000000000000A11",
    vdebt_addr: str = "0x0000000000000000000000000000000000000A33",
) -> tuple:
    """DataTypes.ReserveData (V3) tuple を組み立てるテストヘルパー。

    インデックス: 2=currentLiquidityRate, 4=currentVariableBorrowRate,
    8=aTokenAddress, 10=variableDebtTokenAddress
    """
    return (
        (0,),  # 0: configuration (tuple with single uint256)
        10**27,  # 1: liquidityIndex (1.0 RAY)
        liquidity_rate_ray,  # 2: currentLiquidityRate
        10**27,  # 3: variableBorrowIndex
        variable_borrow_rate_ray,  # 4: currentVariableBorrowRate
        0,  # 5: currentStableBorrowRate
        0,  # 6: lastUpdateTimestamp
        0,  # 7: id
        atoken_addr,  # 8: aTokenAddress
        "0x0000000000000000000000000000000000000A22",  # 9: stableDebtTokenAddress
        vdebt_addr,  # 10: variableDebtTokenAddress
        "0x0000000000000000000000000000000000000A44",  # 11: interestRateStrategyAddress
        0,  # 12: accruedToTreasury
        0,  # 13: unbacked
        0,  # 14: isolationModeTotalDebt
    )


def _make_pool_contract(call_result: tuple) -> MagicMock:
    pool = MagicMock()
    pool.functions.getReserveData.return_value.call.return_value = call_result
    return pool


def _make_erc20_contract(total_supply: int) -> MagicMock:
    erc20 = MagicMock()
    erc20.functions.totalSupply.return_value.call.return_value = total_supply
    return erc20


def test_aave_data_safe_returns_none_dict_on_full_failure():
    """get_default_aave_client が AaveClientError を投げた場合、全 None dict を返すこと。"""
    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        side_effect=AaveClientError("rpc down"),
    ):
        result = fetch_aave_market_data_safe()

    assert result == {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }


def test_aave_data_safe_partial_success_health_factor_only():
    """HF 取得成功 + Pool reserve 取得失敗時、HF のみ値を持つこと。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("1.85")
    # Pool 取得時に最初の contract() 呼出で例外を起こし fail-open させる
    mock_client.w3.eth.contract.side_effect = Exception("aave pool unreachable")

    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        return_value=mock_client,
    ):
        result = fetch_aave_market_data_safe()

    assert result["health_factor"] == Decimal("1.85")
    assert result["utilization_rate"] is None
    assert result["supply_apy"] is None
    assert result["borrow_apy"] is None


def test_aave_data_safe_inf_health_factor_returns_none():
    """HF=inf (借入なし) の場合、health_factor は None になり Pool データは正常取得されること。

    Pool: currentLiquidityRate=5% APR ray, currentVariableBorrowRate=8% APR ray
    aToken.totalSupply = 1,000,000 USDC (1e12 at 6 decimals)
    variableDebtToken.totalSupply = 850,000 USDC → utilization = 85%
    """
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("inf")

    pool_contract = _make_pool_contract(_make_pool_call_result())
    atoken_contract = _make_erc20_contract(1_000_000 * 10**6)
    vdebt_contract = _make_erc20_contract(850_000 * 10**6)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
    ]

    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        return_value=mock_client,
    ):
        result = fetch_aave_market_data_safe()

    assert result["health_factor"] is None
    assert result["utilization_rate"] is not None
    assert abs(result["utilization_rate"] - Decimal("85")) < Decimal("0.01")
    # 5% APR ray → 約 5.127% APY (連続複利近似)
    assert result["supply_apy"] is not None
    assert abs(result["supply_apy"] - Decimal("5.127")) < Decimal("0.01")
    # 8% APR ray → 約 8.328% APY
    assert result["borrow_apy"] is not None
    assert abs(result["borrow_apy"] - Decimal("8.328")) < Decimal("0.01")


def test_aave_data_safe_calls_get_health_factor_no_args():
    """get_health_factor は no-args で呼ばれること (Web3AaveClient は self.account.address を使う)。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.5")
    # Pool 側は失敗させて HF 取得検証に集中
    mock_client.w3.eth.contract.side_effect = Exception("skip")

    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        return_value=mock_client,
    ):
        result = fetch_aave_market_data_safe()

    mock_client.get_health_factor.assert_called_once_with()
    assert result["health_factor"] == Decimal("2.5")


def test_ray_to_apy_conversion():
    """ray スケール APR → APY (%) 変換が連続複利公式と一致すること。

    入力: 50_000_000_000_000_000_000_000_000 (= 5% APR ray)
    期待: APY ≈ 5.127% (誤差 0.01 以内)
    APY = ((1 + 0.05/31_536_000) ** 31_536_000 - 1) * 100 ≈ 5.12710964
    """
    apy = _ray_to_apy_pct(50_000_000_000_000_000_000_000_000)
    assert abs(apy - Decimal("5.127")) < Decimal("0.01")

    # 0 入力は 0 を返す (借入無し / 流動性無しのケース)
    assert _ray_to_apy_pct(0) == Decimal("0")
    assert _ray_to_apy_pct(-1) == Decimal("0")


def test_utilization_zero_when_atoken_zero():
    """aToken.totalSupply = 0 の場合、utilization は 0 を返す (ZeroDivision にしない)。"""
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("3.0")

    pool_contract = _make_pool_contract(_make_pool_call_result())
    atoken_contract = _make_erc20_contract(0)  # totalSupply = 0
    vdebt_contract = _make_erc20_contract(0)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
    ]

    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        return_value=mock_client,
    ):
        result = fetch_aave_market_data_safe()

    assert result["utilization_rate"] == Decimal("0")
    # APY 自体は ray 値から計算されるので supply/borrow APY は 0 でない
    assert result["supply_apy"] is not None
    assert result["borrow_apy"] is not None
