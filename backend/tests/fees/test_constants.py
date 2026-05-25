# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/fees/test_constants.py
"""Tests for app.fees.constants invariants and seed-script alignment (P0-18)."""

from __future__ import annotations

from decimal import Decimal

from app.fees import constants as C


def test_three_tiers() -> None:
    """各 list は LOWER / MIDDLE / UPPER の 3 要素を持つ。"""
    assert len(C.TIER_THRESHOLDS_JPY) == 2, "thresholds は 3 tier の境界 2 個"
    assert len(C.TIER_FEE_RATES) == 3, "tier_fee_rates は 3 要素"
    assert len(C.TIER_MONTHLY_YIELD_CAPS) == 3, "tier_monthly_yield_caps は 3 要素"


def test_thresholds_monotonic_increasing() -> None:
    assert C.TIER_THRESHOLDS_JPY[0] < C.TIER_THRESHOLDS_JPY[1]


def test_fee_rates_monotonic_decreasing() -> None:
    """上位ティアほど低料率 (invariant)。"""
    a, b, c = C.TIER_FEE_RATES
    assert a > b > c, f"tier_fee_rates must be strictly decreasing, got [{a}, {b}, {c}]"


def test_yield_caps_monotonic_increasing() -> None:
    """上位ティアほど高 cap (invariant)。"""
    a, b, c = C.TIER_MONTHLY_YIELD_CAPS
    assert a < b < c, f"tier_monthly_yield_caps must be strictly increasing, got [{a}, {b}, {c}]"


def test_fee_rates_in_reasonable_range() -> None:
    for r in C.TIER_FEE_RATES:
        assert 0.0 < r < 1.0, f"fee rate out of range: {r}"


def test_yield_caps_in_reasonable_range() -> None:
    for r in C.TIER_MONTHLY_YIELD_CAPS:
        assert 0.0 < r < 0.10, f"monthly yield cap out of range (>10%): {r}"


def test_affiliate_rate_is_decimal_and_thirty_percent() -> None:
    assert isinstance(C.AFFILIATE_RATE, Decimal)
    assert C.AFFILIATE_RATE == Decimal("0.30")


def test_expense_markup_default_off() -> None:
    assert C.EXPENSE_MARKUP_ENABLED_DEFAULT is False
    assert C.EXPENSE_MARKUP_RATE_DEFAULT == Decimal("0")


def test_seed_script_uses_constants() -> None:
    """seed_fee_config_v10.py が build した dict と constants が一致する。"""
    from scripts.seed_fee_config_v10 import build_v10_default_config

    cfg = build_v10_default_config()

    assert cfg["tier_thresholds_jpy"] == C.TIER_THRESHOLDS_JPY
    assert cfg["tier_fee_rates"] == C.TIER_FEE_RATES
    assert cfg["tier_monthly_yield_caps"] == C.TIER_MONTHLY_YIELD_CAPS
    assert cfg["affiliate_rate"] == C.AFFILIATE_RATE
    assert cfg["expense_markup_enabled"] == C.EXPENSE_MARKUP_ENABLED_DEFAULT
    assert cfg["expense_markup_rate"] == C.EXPENSE_MARKUP_RATE_DEFAULT
