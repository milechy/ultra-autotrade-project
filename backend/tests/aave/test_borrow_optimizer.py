# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_borrow_optimizer.py
"""
BorrowOptimizer のユニットテスト。

外部 RPC 呼び出しは unittest.mock でモックし、
Decimal 計算の正確性と fail-open 動作を検証する。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.aave.borrow_optimizer import BorrowOptimizer, borrow_currency_signal
from app.aave.schemas import BorrowRateComparison

# 共通テスト定数
_DUMMY_DP_ADDR = "0x2d8A3C5677189723C4cB8873CfC9C8976ddf54D3"
_DUMMY_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_DUMMY_GHO = "0x6Bb7a212910682DCFdbd5BCBb3498A5E2CCEab60"
_DUMMY_STK = "0x4da27a545c0c5B758a6BA100e3a049001de870f5"

# Aave V3 金利は 1e27 (Ray) スケール。APR を Ray に変換するヘルパー
_RAY = 10**27


def _to_ray(apr_decimal: Decimal) -> int:
    """APR (0〜1 の Decimal) を Ray 整数に変換する。"""
    return int(apr_decimal * Decimal(_RAY))


def _make_mock_w3(usdc_variable_apr: Decimal, gho_variable_apr: Decimal) -> MagicMock:
    """
    Web3 インスタンスのモックを生成する。

    getReserveData の戻り値を [0]*6 + [variableBorrowRate_ray] + [0]*5 の形式で返す。
    stkAAVE balanceOf は 0 を返す（割引なし）。
    """
    w3 = MagicMock()

    # USDC の getReserveData 結果
    usdc_result = [0, 0, 0, 0, 0, 0, _to_ray(usdc_variable_apr), 0, 0, 0, 0, 0]
    # GHO の getReserveData 結果
    gho_result = [0, 0, 0, 0, 0, 0, _to_ray(gho_variable_apr), 0, 0, 0, 0, 0]

    def make_dp_contract(address: str, abi: list) -> MagicMock:  # noqa: ARG001
        contract = MagicMock()

        def get_reserve_data(asset_addr: str) -> MagicMock:
            call_mock = MagicMock()
            if asset_addr == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913":
                call_mock.call.return_value = usdc_result
            else:
                call_mock.call.return_value = gho_result
            return call_mock

        contract.functions.getReserveData.side_effect = get_reserve_data
        # stkAAVE balanceOf → 0
        contract.functions.balanceOf.return_value.call.return_value = 0
        return contract

    w3.eth.contract.side_effect = make_dp_contract
    return w3


def _make_optimizer(usdc_apr: Decimal, gho_apr: Decimal) -> BorrowOptimizer:
    """テスト用 BorrowOptimizer を生成する（Web3 モック済み）。"""
    # Web3.to_checksum_address はアドレスをそのまま返すモックにする
    with patch("app.aave.borrow_optimizer.BorrowOptimizer.__init__") as mock_init:
        mock_init.return_value = None
        optimizer = BorrowOptimizer.__new__(BorrowOptimizer)

    optimizer._Web3 = MagicMock()
    optimizer._Web3.to_checksum_address.side_effect = lambda x: x
    optimizer._w3 = _make_mock_w3(usdc_apr, gho_apr)
    optimizer._usdc_address = _DUMMY_USDC
    optimizer._gho_address = _DUMMY_GHO
    optimizer._stk_aave_address = _DUMMY_STK

    # data_provider contract は _w3.eth.contract の最初の呼び出しで返されるものを使う
    optimizer._data_provider = optimizer._w3.eth.contract(address=_DUMMY_DP_ADDR, abi=[])

    return optimizer


# ============================================================================
# get_borrow_rates テスト
# ============================================================================


def test_get_borrow_rates_returns_correct_aprs() -> None:
    """getReserveData の戻り値が正しく APR に変換される。"""
    usdc_apr = Decimal("0.04")  # 4%
    gho_apr = Decimal("0.03")  # 3%
    optimizer = _make_optimizer(usdc_apr, gho_apr)

    result_usdc, result_gho = optimizer.get_borrow_rates()

    # Ray スケール変換の精度は 1e-10 以内で一致するはず
    assert abs(result_usdc - usdc_apr) < Decimal("1e-10"), f"USDC APR mismatch: {result_usdc}"
    assert abs(result_gho - gho_apr) < Decimal("1e-10"), f"GHO APR mismatch: {result_gho}"


# ============================================================================
# get_gho_discount_rate テスト
# ============================================================================


def test_stk_aave_zero_no_discount() -> None:
    """stkAAVE 残高が 0 のとき割引なし（Decimal("0")）を返す。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.03"))
    # stkAAVE balanceOf = 0（モックのデフォルト）
    discount = optimizer.get_gho_discount_rate("0xWalletAddress")
    assert discount == Decimal("0"), f"Expected 0 discount, got {discount}"


def test_empty_wallet_no_discount() -> None:
    """wallet_address が空文字のとき即 Decimal("0") を返す。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.03"))
    discount = optimizer.get_gho_discount_rate("")
    assert discount == Decimal("0")


# ============================================================================
# compare_borrow_rates テスト
# ============================================================================


def test_gho_recommended_when_significantly_cheaper() -> None:
    """GHO APR 3% < USDC APR 4%（差 1% > 0.5%しきい値）→ recommendation="GHO"。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.03"))
    result: BorrowRateComparison = optimizer.compare_borrow_rates(wallet_address="")

    assert result.recommendation == "GHO"
    assert result.annual_savings_usd > Decimal("0")
    assert result.error is None


def test_usdc_recommended_when_gho_more_expensive() -> None:
    """GHO APR 5% > USDC APR 4%（GHO の方が高い）→ recommendation="USDC"。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.05"))
    result: BorrowRateComparison = optimizer.compare_borrow_rates(wallet_address="")

    assert result.recommendation == "USDC"
    assert result.annual_savings_usd == Decimal("0")
    assert result.error is None


def test_usdc_recommended_when_difference_below_threshold() -> None:
    """GHO APR 3.9% / USDC APR 4%（差 0.1% < 0.5%しきい値）→ recommendation="USDC"。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.039"))
    result: BorrowRateComparison = optimizer.compare_borrow_rates(wallet_address="")

    assert result.recommendation == "USDC"
    assert result.annual_savings_usd == Decimal("0")


def test_fail_open_on_rpc_error() -> None:
    """RPC 呼び出し失敗時は fail-open で USDC デフォルト返却（500 にならない）。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.03"))
    # getReserveData を例外送出させる
    optimizer._data_provider.functions.getReserveData.side_effect = Exception("RPC timeout")

    result: BorrowRateComparison = optimizer.compare_borrow_rates(wallet_address="")

    assert result.recommendation == "USDC"
    assert result.error is not None
    assert "RPC" in result.error or "getReserveData" in result.error or "失敗" in result.error


def test_decimal_precision_no_float() -> None:
    """金利計算が Decimal で行われ、APR が 0〜1 の範囲にある。"""
    optimizer = _make_optimizer(Decimal("0.04"), Decimal("0.03"))
    result: BorrowRateComparison = optimizer.compare_borrow_rates()

    # すべての APR フィールドが Decimal
    assert isinstance(result.usdc_apr, Decimal)
    assert isinstance(result.gho_variable_apr, Decimal)
    assert isinstance(result.gho_effective_apr, Decimal)
    assert isinstance(result.annual_savings_usd, Decimal)
    # 0〜1 の範囲
    assert Decimal("0") <= result.usdc_apr <= Decimal("1")
    assert Decimal("0") <= result.gho_effective_apr <= Decimal("1")


# ============================================================================
# borrow_currency_signal テスト
# ============================================================================


def test_signal_recommend_gho() -> None:
    """GHO 実効 APR が USDC より 0.5% 以上有利 → "recommend_gho"。"""
    signal = borrow_currency_signal(
        usdc_apr=Decimal("0.04"),
        gho_effective_apr=Decimal("0.03"),
    )
    assert signal == "recommend_gho"


def test_signal_recommend_usdc_when_gho_expensive() -> None:
    """GHO が USDC より高い → "recommend_usdc"。"""
    signal = borrow_currency_signal(
        usdc_apr=Decimal("0.04"),
        gho_effective_apr=Decimal("0.05"),
    )
    assert signal == "recommend_usdc"


def test_signal_recommend_usdc_when_below_threshold() -> None:
    """差が 0.5% 未満 → "recommend_usdc"（USDC デフォルト）。"""
    signal = borrow_currency_signal(
        usdc_apr=Decimal("0.04"),
        gho_effective_apr=Decimal("0.036"),  # 差 0.4% < 0.5%
    )
    assert signal == "recommend_usdc"


def test_signal_fail_open_on_exception() -> None:
    """不正な引数でも例外を投げず "recommend_usdc" を返す（fail-open）。"""
    # Decimal の演算が失敗するケースをシミュレート
    # (実際には Decimal 同士の演算は例外を出さないが、
    #  この関数の fail-open 挙動を確認するため内部で例外を発生させる)
    with patch("app.aave.borrow_optimizer.logger") as mock_logger:  # noqa: F841
        # 文字列を渡すと Decimal 演算が TypeError になる
        result = borrow_currency_signal(
            usdc_apr="not_a_decimal",  # type: ignore[arg-type]
            gho_effective_apr=Decimal("0.03"),
        )
    assert result == "recommend_usdc"


# ============================================================================
# stkAAVE 非ゼロ残高での割引テスト (Evaluator Nit 3 対応)
# ============================================================================


def _make_optimizer_with_stk_balance(
    usdc_apr: Decimal,
    gho_apr: Decimal,
    stk_balance_tokens: int,
) -> BorrowOptimizer:
    """stkAAVE 残高が非ゼロのテスト用 BorrowOptimizer を生成する。

    balanceOf は 18 decimals = stk_balance_tokens * 10^18 を返す。
    """
    optimizer = _make_optimizer(usdc_apr, gho_apr)
    stk_contract = MagicMock()
    stk_contract.functions.balanceOf.return_value.call.return_value = stk_balance_tokens * (10**18)
    # eth.contract が stkAAVE アドレスで呼ばれたときだけ stk_contract を返す
    original_contract_factory = optimizer._w3.eth.contract.side_effect

    def contract_factory(address: str, abi: list) -> MagicMock:  # noqa: ARG001
        if address == optimizer._stk_aave_address:
            return stk_contract
        if original_contract_factory is not None:
            return original_contract_factory(address=address, abi=abi)
        return MagicMock()

    optimizer._w3.eth.contract.side_effect = contract_factory
    return optimizer


def test_stk_aave_nonzero_applies_discount() -> None:
    """stkAAVE 100 トークン → 1% 割引が適用され GHO 実効 APR が低下する。"""
    # USDC 4%, GHO 3.5% (差 0.5% = しきい値ぴったり、割引なしでは推奨されない)
    optimizer = _make_optimizer_with_stk_balance(Decimal("0.04"), Decimal("0.035"), 100)
    discount = optimizer.get_gho_discount_rate("0xWalletWithStkAave")

    # 100 stkAAVE → 100 / 10000 = 0.01 (1%)
    assert discount == Decimal("0.01"), f"Expected 1% discount, got {discount}"


def test_stk_aave_discount_capped_at_20_percent() -> None:
    """stkAAVE 3000 トークン → 割引上限 20% でキャップされる。"""
    optimizer = _make_optimizer_with_stk_balance(Decimal("0.04"), Decimal("0.03"), 3000)
    discount = optimizer.get_gho_discount_rate("0xWalletWithLargeStkAave")

    # 3000 / 10000 = 0.30 → キャップで 0.20
    assert discount == Decimal("0.20"), f"Expected 20% cap, got {discount}"


def test_stk_aave_discount_reduces_effective_apr() -> None:
    """stkAAVE 割引が compare_borrow_rates の gho_effective_apr に反映される。"""
    # GHO 変動 APR 3%, stkAAVE 200 トークン → 2% 割引 → 実効 APR 3% * (1 - 0.02) = 2.94%
    optimizer = _make_optimizer_with_stk_balance(Decimal("0.04"), Decimal("0.03"), 200)
    result = optimizer.compare_borrow_rates(wallet_address="0xWalletWithStkAave")

    expected_effective = Decimal("0.03") * (Decimal("1") - Decimal("0.02"))
    assert abs(result.gho_effective_apr - expected_effective) < Decimal("1e-10"), (
        f"Expected effective APR {expected_effective}, got {result.gho_effective_apr}"
    )
    # 差 = 4% - 2.94% = 1.06% > 0.5% → GHO 推奨
    assert result.recommendation == "GHO"
