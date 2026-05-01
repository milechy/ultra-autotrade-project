# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Aave マーケットデータ fail-open ヘルパーの単体テスト。

V3 web3 直接呼出 (Pool.getReserveData + ERC20.totalSupply) ベースの実装に対応。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

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
    sdebt_contract = _make_erc20_contract(0)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
        sdebt_contract,
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
    sdebt_contract = _make_erc20_contract(0)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
        sdebt_contract,
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


def test_utilization_includes_stable_debt():
    """utilization に stable debt が含まれること (P2: Aave 公式定義)。

    vdebt = 500_000 USDC (50%), sdebt = 350_000 USDC (35%), atoken = 1_000_000 USDC
    期待 utilization = 85% (旧実装: 50% — バグ)
    """
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.0")

    pool_contract = _make_pool_contract(_make_pool_call_result())
    atoken_contract = _make_erc20_contract(1_000_000 * 10**6)
    vdebt_contract = _make_erc20_contract(500_000 * 10**6)
    sdebt_contract = _make_erc20_contract(350_000 * 10**6)  # 35% stable debt
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
        sdebt_contract,
    ]

    with patch(
        "app.automation.aave_data_fetcher.get_default_aave_client",
        return_value=mock_client,
    ):
        result = fetch_aave_market_data_safe()

    assert result["utilization_rate"] is not None
    assert abs(result["utilization_rate"] - Decimal("85")) < Decimal("0.01"), (
        f"Expected utilization=85 (vdebt 50% + sdebt 35%), got {result['utilization_rate']}"
    )


def test_chain_resolution_uses_client_chain():
    """chain が client.settings.chain_name から解決されること (P1 fix)。

    client.settings.chain_name = "arbitrum" で
    get_active_chains() が base を返す状況でも arbitrum の pool_address が
    pool contract 作成に使われることを確認する。
    """

    Web3 = pytest.importorskip("web3").Web3

    from app.aave.chains import CHAIN_REGISTRY

    arbitrum_config = CHAIN_REGISTRY["arbitrum"]
    base_config = CHAIN_REGISTRY["base"]

    mock_settings = MagicMock()
    mock_settings.chain_name = "arbitrum"
    mock_settings.network = "arbitrum"

    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.0")
    mock_client.settings = mock_settings

    pool_contract = _make_pool_contract(_make_pool_call_result())
    atoken_contract = _make_erc20_contract(1_000_000 * 10**6)
    vdebt_contract = _make_erc20_contract(500_000 * 10**6)
    sdebt_contract = _make_erc20_contract(0)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
        sdebt_contract,
    ]

    with (
        patch(
            "app.automation.aave_data_fetcher.get_default_aave_client",
            return_value=mock_client,
        ),
        patch(
            "app.automation.aave_data_fetcher.get_active_chains",
            return_value=[base_config],
        ),
    ):
        result = fetch_aave_market_data_safe()

    # 最初の contract() 呼出 (pool contract) が arbitrum の pool_address を使っているか確認
    first_call = mock_client.w3.eth.contract.call_args_list[0]
    expected_pool_addr = Web3.to_checksum_address(arbitrum_config.pool_address)
    actual_pool_addr = first_call.kwargs.get("address") or (
        first_call.args[0] if first_call.args else None
    )
    assert actual_pool_addr == expected_pool_addr, (
        f"Expected arbitrum pool {expected_pool_addr}, got {actual_pool_addr}. "
        "P1 fix: client.settings.chain_name must override get_active_chains()[0]"
    )

    # get_active_chains が返した base_config の pool は使われていないことも確認
    base_pool_addr = Web3.to_checksum_address(base_config.pool_address)
    assert actual_pool_addr != base_pool_addr, (
        "base pool address was used instead of arbitrum — P1 fix not working"
    )

    # 正常に utilization が返ること
    assert result["utilization_rate"] is not None


def test_zero_address_stable_debt_skipped():
    """stableDebtTokenAddress が 0x000...000 の場合、contract 呼出をスキップして sdebt=0 とすること。

    Aave V3.3+ の deprecated reserve では stableDebtTokenAddress が zero address になる。
    zero-code アドレスに totalSupply() を呼ぶと ABI decode 失敗で全フィールド None になるため、
    zero address は呼出をスキップして 0 debt として扱う (Codex P1 fix)。

    atoken = 1_000_000 USDC, vdebt = 500_000 USDC (50%), sdebt addr = 0x000...000
    期待 utilization = 50% (sdebt 呼出なし)
    w3.eth.contract の呼出回数 = 3 (pool / atoken / vdebt のみ)
    """
    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.0")

    pool_contract = _make_pool_contract(
        _make_pool_call_result(
            # stableDebtTokenAddress を zero address に設定 (index 9)
        )
    )
    # _make_pool_call_result の index 9 を zero address に上書き
    zero_addr = "0x0000000000000000000000000000000000000000"
    call_result = list(_make_pool_call_result())
    call_result[9] = zero_addr
    pool_contract = _make_pool_contract(tuple(call_result))

    atoken_contract = _make_erc20_contract(1_000_000 * 10**6)
    vdebt_contract = _make_erc20_contract(500_000 * 10**6)
    # sdebt contract は渡さない — 呼ばれたら StopIteration で検出できる
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

    # sdebt 呼出がなく contract() は 3 回のみ (pool / atoken / vdebt)
    assert mock_client.w3.eth.contract.call_count == 3, (
        f"Expected 3 contract() calls (pool/atoken/vdebt), "
        f"got {mock_client.w3.eth.contract.call_count}"
    )
    # utilization = vdebt のみ = 50%
    assert result["utilization_rate"] is not None
    assert abs(result["utilization_rate"] - Decimal("50")) < Decimal("0.01"), (
        f"Expected utilization=50 (vdebt only, sdebt skipped), got {result['utilization_rate']}"
    )


def test_chain_resolution_normalizes_hyphen_to_underscore():
    """client.settings.network = "base-sepolia" (ハイフン) でも CHAIN_REGISTRY["base_sepolia"] にヒットすること。

    staging 環境で network="base-sepolia" が返るが CHAIN_REGISTRY のキーは "base_sepolia"
    (アンダースコア) のため lookup miss → arbitrum フォールバックになっていた。
    正規化で base_sepolia の pool_address が使われることを確認する。
    """
    Web3 = pytest.importorskip("web3").Web3

    from app.aave.chains import CHAIN_REGISTRY

    base_sepolia_config = CHAIN_REGISTRY["base_sepolia"]
    arbitrum_config = CHAIN_REGISTRY["arbitrum"]

    mock_settings = MagicMock()
    mock_settings.chain_name = None
    mock_settings.network = "base-sepolia"  # ハイフン区切り

    mock_client = MagicMock()
    mock_client.get_health_factor.return_value = Decimal("2.0")
    mock_client.settings = mock_settings

    pool_contract = _make_pool_contract(_make_pool_call_result())
    atoken_contract = _make_erc20_contract(1_000_000 * 10**6)
    vdebt_contract = _make_erc20_contract(500_000 * 10**6)
    sdebt_contract = _make_erc20_contract(0)
    mock_client.w3.eth.contract.side_effect = [
        pool_contract,
        atoken_contract,
        vdebt_contract,
        sdebt_contract,
    ]

    with (
        patch(
            "app.automation.aave_data_fetcher.get_default_aave_client",
            return_value=mock_client,
        ),
        patch(
            "app.automation.aave_data_fetcher.get_active_chains",
            return_value=[arbitrum_config],  # フォールバック先は arbitrum
        ),
    ):
        result = fetch_aave_market_data_safe()

    first_call = mock_client.w3.eth.contract.call_args_list[0]
    expected_pool_addr = Web3.to_checksum_address(base_sepolia_config.pool_address)
    actual_pool_addr = first_call.kwargs.get("address") or (
        first_call.args[0] if first_call.args else None
    )
    assert actual_pool_addr == expected_pool_addr, (
        f"Expected base_sepolia pool {expected_pool_addr}, got {actual_pool_addr}. "
        "hyphen normalization must resolve 'base-sepolia' → CHAIN_REGISTRY['base_sepolia']"
    )

    arbitrum_pool_addr = Web3.to_checksum_address(arbitrum_config.pool_address)
    assert actual_pool_addr != arbitrum_pool_addr, (
        "arbitrum pool was used instead of base_sepolia — hyphen normalization not working"
    )

    assert result["utilization_rate"] is not None
