# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.aave.net_benefit_calculator import NetBenefitCalculator, NetBenefitParams
from app.aave.optimization_rules import CurrentPosition, OptimizationRules, ProposedAction

# ---------------------------------------------------------------------------
# Net Benefit Calculator
# ---------------------------------------------------------------------------


def _stable_params(**overrides) -> NetBenefitParams:
    defaults = dict(
        asset_symbol="USDC",
        amount=Decimal("10000"),
        supply_apy=Decimal("0.05"),
        incentive_apy=Decimal("0.01"),
        gas_cost_usd=Decimal("5"),
        holding_period_days=30,
        volatility_30d=Decimal("0.01"),
        depeg_distance=Decimal("0.001"),
    )
    defaults.update(overrides)
    return NetBenefitParams(**defaults)


def test_net_benefit_positive() -> None:
    calc = NetBenefitCalculator()
    result = calc.calculate(_stable_params())
    assert result.net_benefit > Decimal("0")


def test_net_benefit_negative() -> None:
    calc = NetBenefitCalculator()
    # Very small amount, very high gas cost → negative
    params = _stable_params(amount=Decimal("10"), gas_cost_usd=Decimal("500"))
    result = calc.calculate(params)
    assert result.net_benefit < Decimal("0")


def test_net_benefit_volatile_asset() -> None:
    calc = NetBenefitCalculator()
    stable = _stable_params(amount=Decimal("10000"), depeg_distance=Decimal("0"))
    eth_params = NetBenefitParams(
        asset_symbol="ETH",
        amount=Decimal("10000"),
        supply_apy=Decimal("0.03"),
        incentive_apy=Decimal("0.01"),
        gas_cost_usd=Decimal("5"),
        holding_period_days=30,
        volatility_30d=Decimal("0.30"),
        depeg_distance=Decimal("0"),
    )
    stable_result = calc.calculate(stable)
    eth_result = calc.calculate(eth_params)
    # ETH risk penalty should be higher → lower net_benefit
    assert eth_result.risk_penalty > stable_result.risk_penalty


def test_net_benefit_all_decimal() -> None:
    calc = NetBenefitCalculator()
    result = calc.calculate(_stable_params())
    for field in (
        "expected_revenue",
        "execution_cost",
        "risk_penalty",
        "net_benefit",
        "annualized_net_rate",
    ):
        assert isinstance(getattr(result, field), Decimal), f"{field} should be Decimal"


# ---------------------------------------------------------------------------
# Optimization Rules
# ---------------------------------------------------------------------------


def _make_position(net_rate: Decimal, hours_ago: float = 48.0) -> CurrentPosition:
    return CurrentPosition(
        asset_symbol="USDC",
        amount=Decimal("5000"),
        current_apy=Decimal("0.04"),
        net_rate=net_rate,
        last_action_at=datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago),
    )


def _make_proposal(net_rate: Decimal, amount: Decimal = Decimal("1000")) -> ProposedAction:
    return ProposedAction(
        asset_symbol="DAI",
        amount=amount,
        net_rate=net_rate,
        action_type="SUPPLY",
    )


def test_rules_min_improvement() -> None:
    rules = OptimizationRules()
    current = _make_position(net_rate=Decimal("0.05"))
    proposed = _make_proposal(net_rate=Decimal("0.055"))  # +0.5%, below 1% threshold
    result = rules.should_rebalance(current, proposed, total_assets=Decimal("10000"))
    assert not result.allowed
    assert "min_improvement" in result.checks_failed


def test_rules_min_holding() -> None:
    rules = OptimizationRules()
    current = _make_position(net_rate=Decimal("0.04"), hours_ago=12.0)  # only 12h held
    proposed = _make_proposal(net_rate=Decimal("0.06"))
    result = rules.should_rebalance(current, proposed, total_assets=Decimal("10000"))
    assert not result.allowed
    assert "min_holding" in result.checks_failed


def test_rules_partial_move() -> None:
    rules = OptimizationRules()
    current = _make_position(net_rate=Decimal("0.04"))
    proposed = _make_proposal(net_rate=Decimal("0.06"), amount=Decimal("5000"))  # 50% of 10000
    result = rules.should_rebalance(current, proposed, total_assets=Decimal("10000"))
    assert not result.allowed
    assert "partial_move" in result.checks_failed


def test_rules_hysteresis() -> None:
    rules = OptimizationRules()
    current = _make_position(net_rate=Decimal("0.05"))
    # diff = 0.003 < 0.005 hysteresis threshold, but also < 0.01 improvement → both fail
    # To isolate hysteresis, use a rate just above MIN_IMPROVEMENT_RATE but below HYSTERESIS...
    # Actually hysteresis (0.5%) and min_improvement (1%) — if diff < hysteresis then diff < improvement too.
    # Let's just confirm hysteresis is in checks_failed when diff is small
    proposed = _make_proposal(net_rate=Decimal("0.053"))  # diff=0.003 < 0.005
    result = rules.should_rebalance(current, proposed, total_assets=Decimal("10000"))
    assert not result.allowed
    assert "hysteresis" in result.checks_failed


def test_rules_all_pass() -> None:
    rules = OptimizationRules()
    current = _make_position(net_rate=Decimal("0.04"), hours_ago=48.0)
    proposed = _make_proposal(net_rate=Decimal("0.06"), amount=Decimal("2000"))  # 20% of 10000
    result = rules.should_rebalance(current, proposed, total_assets=Decimal("10000"))
    assert result.allowed
    assert result.checks_failed == []
