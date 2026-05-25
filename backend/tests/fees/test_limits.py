# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/fees/test_limits.py
"""Tests for app.fees.limits (P0-3.1)."""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest

from app.fees import limits


def test_defaults_are_decimal_and_positive() -> None:
    assert isinstance(limits.PER_USER_MAX_DEPOSIT_USD, Decimal)
    assert isinstance(limits.TVL_CAP_USD, Decimal)
    assert isinstance(limits.ALERT_THRESHOLD_RATIO, Decimal)
    assert limits.PER_USER_MAX_DEPOSIT_USD > 0
    assert limits.TVL_CAP_USD > 0
    assert Decimal("0") < limits.ALERT_THRESHOLD_RATIO <= Decimal("1")


def test_deposit_zero_amount_rejected() -> None:
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("0"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("0"),
    )
    assert d.allowed is False
    assert "入金額" in d.reason


def test_deposit_negative_amount_rejected() -> None:
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("-1"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("0"),
    )
    assert d.allowed is False


def test_deposit_within_per_user_cap_allowed() -> None:
    # user_remaining_usd / tvl_headroom_usd は *入金前* の残り余地 (docstring 明示)。
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("100"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("0"),
        per_user_cap_usd=Decimal("200"),
        tvl_cap_usd=Decimal("10000"),
    )
    assert d.allowed is True
    assert d.user_remaining_usd == Decimal("200")
    assert d.tvl_headroom_usd == Decimal("10000")


def test_deposit_exactly_at_per_user_cap_allowed() -> None:
    # 入金前残り = 200 - 0 = 200。requested 200 はちょうど cap に乗る境界条件。
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("200"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("0"),
        per_user_cap_usd=Decimal("200"),
        tvl_cap_usd=Decimal("10000"),
    )
    assert d.allowed is True
    assert d.user_remaining_usd == Decimal("200")


def test_deposit_over_per_user_cap_rejected() -> None:
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("100"),
        user_current_deposit_usd=Decimal("150"),
        current_tvl_usd=Decimal("0"),
        per_user_cap_usd=Decimal("200"),
        tvl_cap_usd=Decimal("10000"),
    )
    assert d.allowed is False
    assert "入金上限" in d.reason
    assert d.user_remaining_usd == Decimal("50")


def test_deposit_over_tvl_cap_rejected() -> None:
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("100"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("9950"),
        per_user_cap_usd=Decimal("200"),
        tvl_cap_usd=Decimal("10000"),
    )
    assert d.allowed is False
    assert "TVL" in d.reason
    assert d.tvl_headroom_usd == Decimal("50")


def test_deposit_exactly_at_tvl_cap_allowed() -> None:
    d = limits.check_deposit_allowed(
        requested_amount_usd=Decimal("50"),
        user_current_deposit_usd=Decimal("0"),
        current_tvl_usd=Decimal("9950"),
        per_user_cap_usd=Decimal("200"),
        tvl_cap_usd=Decimal("10000"),
    )
    assert d.allowed is True


def test_alert_below_threshold() -> None:
    assert (
        limits.tvl_alert_should_fire(
            current_tvl_usd=Decimal("100"),
            tvl_cap_usd=Decimal("1000"),
            threshold_ratio=Decimal("0.5"),
        )
        is False
    )


def test_alert_at_threshold_fires() -> None:
    assert (
        limits.tvl_alert_should_fire(
            current_tvl_usd=Decimal("500"),
            tvl_cap_usd=Decimal("1000"),
            threshold_ratio=Decimal("0.5"),
        )
        is True
    )


def test_alert_zero_cap_returns_false() -> None:
    assert (
        limits.tvl_alert_should_fire(
            current_tvl_usd=Decimal("0"),
            tvl_cap_usd=Decimal("0"),
        )
        is False
    )


def test_env_override_per_user_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PER_USER_MAX_DEPOSIT_USD", "500")
    monkeypatch.setenv("INITIAL_USER_COUNT", "10")
    monkeypatch.setenv("TVL_CAP_USD", "")  # 未設定で default = per_user * count
    reloaded = importlib.reload(limits)
    try:
        assert reloaded.PER_USER_MAX_DEPOSIT_USD == Decimal("500")
        assert reloaded.INITIAL_USER_COUNT == 10
        assert reloaded.TVL_CAP_USD == Decimal("5000")
    finally:
        # 他テストへの汚染を避けるため reload で元に戻す
        for k in ("PER_USER_MAX_DEPOSIT_USD", "INITIAL_USER_COUNT", "TVL_CAP_USD"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(limits)


def test_env_override_invalid_falls_back() -> None:
    # _env_decimal は不正値で default に fallback する
    assert limits._env_decimal("__UNSET_KEY__", Decimal("42")) == Decimal("42")
