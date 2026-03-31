# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_slippage_guard.py
"""Tests for SlippageGuard."""

from decimal import Decimal

from app.aave.slippage_guard import SlippageGuard


def test_no_deviation_passes():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("ETH", Decimal("2000.00"))
    assert guard.check_post_price("ETH", Decimal("2000.00")) is True


def test_within_threshold_passes():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("ETH", Decimal("2000.00"))
    # 1.5% deviation → OK
    assert guard.check_post_price("ETH", Decimal("1970.00")) is True


def test_exceeds_threshold_blocks():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("ETH", Decimal("2000.00"))
    # 3% deviation → blocked
    assert guard.check_post_price("ETH", Decimal("1940.00")) is False


def test_no_pre_price_allows():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    # pre_price 未記録 → 許可（安全側）
    assert guard.check_post_price("ETH", Decimal("2000.00")) is True


def test_stablecoin_small_deviation():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("USDC", Decimal("1.00"))
    # $0.99 → 1% deviation → OK
    assert guard.check_post_price("USDC", Decimal("0.99")) is True


def test_stablecoin_large_deviation():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("USDC", Decimal("1.00"))
    # $0.95 → 5% deviation → blocked
    assert guard.check_post_price("USDC", Decimal("0.95")) is False


def test_clear_prices():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("USDC", Decimal("1.00"))
    guard.clear("USDC")
    # クリア後は pre_price がないので許可
    assert guard.check_post_price("USDC", Decimal("0.90")) is True


def test_decimal_only():
    guard = SlippageGuard(max_deviation_pct=Decimal("2.0"))
    guard.record_pre_price("ETH", Decimal("2000"))
    # Decimal型であることを確認
    assert isinstance(guard.max_deviation_pct, Decimal)
    assert isinstance(guard._pre_operation_prices["ETH"], Decimal)
