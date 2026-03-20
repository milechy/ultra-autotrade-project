# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_exchange_fee_calculator.py

from decimal import Decimal

from app.exchange.fee_calculator import PerformanceFeeCalculator, TradingFeeCalculator

# ---------------------------------------------------------------------------
# TradingFeeCalculator
# ---------------------------------------------------------------------------


def test_trading_fee_maker():
    calc = TradingFeeCalculator(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
    fee = calc.calculate_maker_fee(Decimal("1000"))
    assert fee == Decimal("1")


def test_trading_fee_taker():
    calc = TradingFeeCalculator(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
    fee = calc.calculate_taker_fee(Decimal("1000"))
    assert fee == Decimal("2")


def test_trading_fee_round_trip():
    calc = TradingFeeCalculator(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.001"))
    fee = calc.calculate_round_trip_fee(Decimal("1000"))
    # (0.001 + 0.001) * 1000 * 2 = 4
    assert fee == Decimal("4")


def test_trading_fee_zero_amount():
    calc = TradingFeeCalculator()
    assert calc.calculate_maker_fee(Decimal("0")) == Decimal("0")
    assert calc.calculate_taker_fee(Decimal("0")) == Decimal("0")
    assert calc.calculate_round_trip_fee(Decimal("0")) == Decimal("0")


def test_trading_fee_large_amount_precision():
    calc = TradingFeeCalculator(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.001"))
    fee = calc.calculate_maker_fee(Decimal("1000000"))
    assert fee == Decimal("1000")


def test_trading_fee_default_rates():
    calc = TradingFeeCalculator()
    fee = calc.calculate_maker_fee(Decimal("500"))
    assert fee == Decimal("0.5")


# ---------------------------------------------------------------------------
# PerformanceFeeCalculator
# ---------------------------------------------------------------------------


def test_performance_fee_zero_profit():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("1000"))
    fee = calc.calculate_performance_fee(Decimal("1000"))
    assert fee == Decimal("0")


def test_performance_fee_negative_profit():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("1000"))
    fee = calc.calculate_performance_fee(Decimal("900"))
    assert fee == Decimal("0")


def test_performance_fee_positive_profit():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("1000"))
    fee = calc.calculate_performance_fee(Decimal("1200"))
    # (1200 - 1000) * 0.20 = 40
    assert fee == Decimal("40")


def test_hwm_only_increases():
    calc = PerformanceFeeCalculator(initial_hwm=Decimal("1000"))
    calc.update_hwm(Decimal("1500"))
    assert calc.hwm == Decimal("1500")
    calc.update_hwm(Decimal("1200"))
    assert calc.hwm == Decimal("1500")


def test_hwm_not_updated_by_calculate():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("1000"))
    calc.calculate_performance_fee(Decimal("1500"))
    # HWM should still be 1000 because calculate_performance_fee does not update it
    assert calc.hwm == Decimal("1000")


def test_hwm_updated_by_update_hwm():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("1000"))
    calc.calculate_performance_fee(Decimal("1500"))
    calc.update_hwm(Decimal("1500"))
    assert calc.hwm == Decimal("1500")


def test_decimal_precision():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.20"), initial_hwm=Decimal("0"))
    fee = calc.calculate_performance_fee(Decimal("100.5"))
    # 100.5 * 0.20 = 20.10
    assert fee == Decimal("20.10")


def test_custom_fee_rate_10_percent():
    calc = PerformanceFeeCalculator(fee_rate=Decimal("0.10"), initial_hwm=Decimal("500"))
    fee = calc.calculate_performance_fee(Decimal("600"))
    # (600 - 500) * 0.10 = 10
    assert fee == Decimal("10")


def test_initial_hwm_parameter():
    calc = PerformanceFeeCalculator(initial_hwm=Decimal("5000"))
    assert calc.hwm == Decimal("5000")
    fee = calc.calculate_performance_fee(Decimal("4999"))
    assert fee == Decimal("0")


def test_hwm_starts_at_zero_by_default():
    calc = PerformanceFeeCalculator()
    assert calc.hwm == Decimal("0")
    fee = calc.calculate_performance_fee(Decimal("100"))
    # (100 - 0) * 0.20 = 20
    assert fee == Decimal("20")