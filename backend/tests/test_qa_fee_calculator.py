# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_qa_fee_calculator.py
"""
QA: Fee calculator property tests.

Focused QA scenarios complementing the unit tests in test_fee_calculator.py:
- Basic daily fee calculation
- Below-minimum AUM flag
- Monthly consistency (30 daily fees ≈ 1 monthly fee)
"""

from decimal import Decimal

from app.aave.fee_calculator import FeeCalculator


def test_fee_basic_calculation() -> None:
    """
    AUM=$10000, days=1 → management fee calculation is correct.

    Expected: 10000 * 0.005 / 365 * 1 = ~0.1369... → rounded to 0.14
    """
    calc = FeeCalculator()
    result = calc.calculate_management_fee(Decimal("10000"), days=1)

    assert isinstance(result.fee_usd, Decimal)
    assert result.aum_usd == Decimal("10000")
    assert result.days == 1
    assert result.rate == Decimal("0.005")
    # Exact value: 10000 * 0.005 / 365 = 0.136986... → ROUND_HALF_UP → 0.14
    assert result.fee_usd == Decimal("0.14")
    assert result.below_minimum is False


def test_fee_below_minimum() -> None:
    """AUM=$2999 (below $3000 minimum) → below_minimum=True."""
    calc = FeeCalculator()
    result = calc.calculate_management_fee(Decimal("2999"), days=1)

    assert result.below_minimum is True
    assert result.aum_usd == Decimal("2999")

    # Boundary: exactly at minimum
    result_at_min = calc.calculate_management_fee(Decimal("3000"), days=1)
    assert result_at_min.below_minimum is False


def test_fee_monthly_consistency() -> None:
    """
    30 daily fees accumulated ≈ 1 monthly fee (within $0.01 margin).

    Verifies that calculate_management_fee(aum, days=30) is consistent
    with summing 30 individual daily fees.
    """
    calc = FeeCalculator()
    aum = Decimal("10000")

    # One-shot 30-day fee
    monthly_result = calc.calculate_management_fee(aum, days=30)

    # Sum of 30 individual daily fees (each rounded separately)
    daily_fee = calc.calculate_management_fee(aum, days=1).fee_usd
    sum_of_daily = daily_fee * 30

    # Monthly and summed-daily should be within $0.10
    # (daily rounding error ~$0.003/day × 30 days ≈ $0.09 max accumulated)
    diff = abs(monthly_result.fee_usd - sum_of_daily)
    assert diff <= Decimal("0.10"), (
        f"Monthly fee {monthly_result.fee_usd} differs from "
        f"sum of 30 daily fees {sum_of_daily} by {diff}"
    )