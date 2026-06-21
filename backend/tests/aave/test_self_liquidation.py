# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_self_liquidation.py
"""自己清算保護（Flash Loan デレバレッジ）純計算の単体テスト（Asana 1215620828227794 第1スライス）。

返済額の解析解が目標 HF を正しく回復すること、各種 fail-closed 分岐、HF 計算・発動判定を検証。
金融計算はすべて Decimal。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.aave.self_liquidation import (
    DEFAULT_TARGET_HF,
    DeleverageQuote,
    SelfLiquidationError,
    compute_deleverage_quote,
    compute_health_factor,
    should_protect,
)

# ---- compute_health_factor ----


def test_hf_basic() -> None:
    hf = compute_health_factor(Decimal("1000"), Decimal("500"), Decimal("0.8"))
    assert hf == Decimal("1.6")


def test_hf_no_debt_is_none() -> None:
    assert compute_health_factor(Decimal("1000"), Decimal("0"), Decimal("0.8")) is None


# ---- should_protect ----


def test_should_protect_below_trigger() -> None:
    assert should_protect(Decimal("1.2")) is True


def test_should_protect_at_or_above_trigger() -> None:
    assert should_protect(Decimal("1.3")) is False
    assert should_protect(Decimal("1.6")) is False


def test_should_protect_no_debt() -> None:
    assert should_protect(None) is False


def test_should_protect_custom_trigger() -> None:
    assert should_protect(Decimal("1.55"), trigger_hf=Decimal("1.6")) is True


# ---- compute_deleverage_quote: feasible ----


def test_partial_deleverage_restores_target_hf() -> None:
    """部分返済で projected_hf が目標 HF に一致する（解析解の検算）。"""
    q = compute_deleverage_quote(
        collateral_usd=Decimal("1000"),
        debt_usd=Decimal("900"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert q.feasible is True
    assert q.repay_debt_usd < Decimal("900")  # 部分返済
    assert q.flash_loan_fee_usd == q.repay_debt_usd * Decimal("0.0005")
    assert q.collateral_withdraw_usd == q.repay_debt_usd + q.flash_loan_fee_usd
    assert q.projected_hf is not None
    # 目標 1.8 にほぼ一致
    assert abs(q.projected_hf - DEFAULT_TARGET_HF) < Decimal("0.001")


def test_custom_target_hf() -> None:
    q = compute_deleverage_quote(
        collateral_usd=Decimal("1000"),
        debt_usd=Decimal("900"),
        liquidation_threshold=Decimal("0.8"),
        target_hf=Decimal("2.0"),
    )
    assert q.feasible is True
    assert q.projected_hf is not None
    assert abs(q.projected_hf - Decimal("2.0")) < Decimal("0.001")


# ---- compute_deleverage_quote: not feasible ----


def test_no_debt_not_feasible() -> None:
    q = compute_deleverage_quote(
        collateral_usd=Decimal("1000"),
        debt_usd=Decimal("0"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert q.feasible is False
    assert q.repay_debt_usd == Decimal("0")
    assert "no debt" in q.reason


def test_hf_already_safe_not_feasible() -> None:
    q = compute_deleverage_quote(
        collateral_usd=Decimal("10000"),
        debt_usd=Decimal("1000"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert q.feasible is False
    assert q.projected_hf == Decimal("8")  # HF=8 ≥ target
    assert "already" in q.reason


def test_insufficient_collateral_not_feasible() -> None:
    """深く水没（collateral < 必要引出額）だと自己清算では救えず fail-closed。"""
    q = compute_deleverage_quote(
        collateral_usd=Decimal("500"),
        debt_usd=Decimal("600"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert q.feasible is False
    assert q.repay_debt_usd == Decimal("0")
    assert "insufficient collateral" in q.reason


def test_target_unreachable_for_threshold() -> None:
    """target_hf <= (1+fee)*lt の病的ケースは到達不能。"""
    q = compute_deleverage_quote(
        collateral_usd=Decimal("400"),
        debt_usd=Decimal("1000"),
        liquidation_threshold=Decimal("0.8"),
        target_hf=Decimal("0.5"),
    )
    assert q.feasible is False
    assert "not reachable" in q.reason


# ---- input validation ----


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "collateral_usd": Decimal("-1"),
            "debt_usd": Decimal("1"),
            "liquidation_threshold": Decimal("0.8"),
        },
        {
            "collateral_usd": Decimal("1"),
            "debt_usd": Decimal("-1"),
            "liquidation_threshold": Decimal("0.8"),
        },
        {
            "collateral_usd": Decimal("1"),
            "debt_usd": Decimal("1"),
            "liquidation_threshold": Decimal("0"),
        },
        {
            "collateral_usd": Decimal("1"),
            "debt_usd": Decimal("1"),
            "liquidation_threshold": Decimal("1.5"),
        },
        {
            "collateral_usd": Decimal("1"),
            "debt_usd": Decimal("1"),
            "liquidation_threshold": Decimal("0.8"),
            "target_hf": Decimal("0"),
        },
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(SelfLiquidationError):
        compute_deleverage_quote(**kwargs)


def test_quote_is_frozen() -> None:
    q = compute_deleverage_quote(
        collateral_usd=Decimal("1000"),
        debt_usd=Decimal("900"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert isinstance(q, DeleverageQuote)
    with pytest.raises(Exception):
        q.feasible = False  # type: ignore[misc]
