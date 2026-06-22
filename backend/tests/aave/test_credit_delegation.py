# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_credit_delegation.py
"""Credit Delegation 安全枠計算の単体テスト（Asana 1215620587799245 第1スライス）。

HF floor 上限・絶対委譲上限の二重クランプ、借入後 HF、fail-closed、入力検証を Decimal で検証。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.aave.credit_delegation import (
    DEFAULT_HF_FLOOR,
    CreditDelegationError,
    assess_delegated_borrow,
    compute_max_delegated_borrow,
)

# ---- compute_max_delegated_borrow ----


def test_max_borrow_basic() -> None:
    # collateral*lt/floor - debt = 1000*0.8/1.6 - 0 = 500
    m = compute_max_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert m == Decimal("500")


def test_max_borrow_with_existing_debt() -> None:
    # 1000*0.8/1.6 - 200 = 300
    m = compute_max_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("200"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert m == Decimal("300")


def test_max_borrow_floored_at_zero() -> None:
    # 既に floor を割る水準 → 追加借入余地 0
    m = compute_max_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("600"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert m == Decimal("0")


# ---- assess_delegated_borrow ----


def test_full_approval_within_floor() -> None:
    a = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        requested_borrow_usd=Decimal("400"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert a.approved_usd == Decimal("400")
    assert a.max_borrow_usd == Decimal("500")
    assert a.within_floor is True
    assert a.projected_hf is not None and a.projected_hf >= DEFAULT_HF_FLOOR
    assert "fully approved" in a.reason


def test_clamped_by_hf_floor() -> None:
    a = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        requested_borrow_usd=Decimal("800"),  # > max 500
        liquidation_threshold=Decimal("0.8"),
    )
    assert a.approved_usd == Decimal("500")
    assert a.within_floor is True
    # 借入後 HF はちょうど floor
    assert a.projected_hf == DEFAULT_HF_FLOOR
    assert "HF floor" in a.reason


def test_clamped_by_delegation_cap() -> None:
    a = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        requested_borrow_usd=Decimal("400"),
        liquidation_threshold=Decimal("0.8"),
        delegation_cap_usd=Decimal("250"),  # 絶対上限が更に厳しい
    )
    assert a.approved_usd == Decimal("250")
    assert "delegation cap" in a.reason
    assert a.within_floor is True


def test_no_headroom() -> None:
    a = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("600"),  # 既に floor 割れ水準
        requested_borrow_usd=Decimal("100"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert a.approved_usd == Decimal("0")
    assert a.max_borrow_usd == Decimal("0")
    assert "no borrow headroom" in a.reason


def test_zero_request_no_debt_hf_none() -> None:
    a = assess_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        requested_borrow_usd=Decimal("0"),
        liquidation_threshold=Decimal("0.8"),
    )
    assert a.approved_usd == Decimal("0")
    assert a.projected_hf is None  # debt=0 → HF 無限大
    assert a.within_floor is True


def test_custom_hf_floor() -> None:
    # floor 2.0: max = 1000*0.8/2.0 = 400
    m = compute_max_delegated_borrow(
        collateral_usd=Decimal("1000"),
        existing_debt_usd=Decimal("0"),
        liquidation_threshold=Decimal("0.8"),
        hf_floor=Decimal("2.0"),
    )
    assert m == Decimal("400")


# ---- input validation ----


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "collateral_usd": Decimal("-1"),
            "existing_debt_usd": Decimal("0"),
            "liquidation_threshold": Decimal("0.8"),
        },
        {
            "collateral_usd": Decimal("1"),
            "existing_debt_usd": Decimal("-1"),
            "liquidation_threshold": Decimal("0.8"),
        },
        {
            "collateral_usd": Decimal("1"),
            "existing_debt_usd": Decimal("0"),
            "liquidation_threshold": Decimal("0"),
        },
        {
            "collateral_usd": Decimal("1"),
            "existing_debt_usd": Decimal("0"),
            "liquidation_threshold": Decimal("1.1"),
        },
        {
            "collateral_usd": Decimal("1"),
            "existing_debt_usd": Decimal("0"),
            "liquidation_threshold": Decimal("0.8"),
            "hf_floor": Decimal("0"),
        },
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(CreditDelegationError):
        compute_max_delegated_borrow(**kwargs)


def test_negative_request_raises() -> None:
    with pytest.raises(CreditDelegationError):
        assess_delegated_borrow(
            collateral_usd=Decimal("1000"),
            existing_debt_usd=Decimal("0"),
            requested_borrow_usd=Decimal("-1"),
            liquidation_threshold=Decimal("0.8"),
        )
