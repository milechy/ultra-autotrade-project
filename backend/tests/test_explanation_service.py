from __future__ import annotations

from decimal import Decimal

from app.ai.explanation_service import ExplanationContext, ExplanationService


def _ctx(**kwargs) -> ExplanationContext:
    defaults = dict(
        action="HOLD",
        utilization_rate=Decimal("0.65"),
        supply_apy=Decimal("0.05"),
        volatility_30d=Decimal("0.04"),
        impact_with=Decimal("10.00"),
        impact_without=Decimal("8.00"),
        impact_difference=Decimal("2.00"),
        asset_symbol="USDC",
    )
    defaults.update(kwargs)
    return ExplanationContext(**defaults)


svc = ExplanationService()


def test_conclusion_buy() -> None:
    result = svc.generate(_ctx(action="BUY"))
    assert "預ける" in result.conclusion


def test_conclusion_sell() -> None:
    result = svc.generate(_ctx(action="SELL"))
    assert "引き出す" in result.conclusion


def test_conclusion_hold() -> None:
    result = svc.generate(_ctx(action="HOLD"))
    assert "様子を見る" in result.conclusion


def test_reason_high_util() -> None:
    result = svc.generate(_ctx(utilization_rate=Decimal("0.85")))
    assert "借りる人が多い" in result.reason


def test_reason_low_util() -> None:
    result = svc.generate(_ctx(utilization_rate=Decimal("0.30")))
    assert "借りる人が少な" in result.reason


def test_reason_high_vol() -> None:
    result = svc.generate(_ctx(volatility_30d=Decimal("0.12")))
    assert "不安定" in result.reason


def test_risks_list() -> None:
    result = svc.generate(_ctx())
    assert isinstance(result.risks, list)
    assert len(result.risks) > 0


def test_signal_sunny() -> None:
    sig = svc.generate_signal(
        _ctx(action="BUY", utilization_rate=Decimal("0.85"), volatility_30d=Decimal("0.03"))
    )
    assert sig.icon == "☀️"
    assert sig.weather == "sunny"


def test_signal_cloudy() -> None:
    sig = svc.generate_signal(
        _ctx(action="HOLD", utilization_rate=Decimal("0.65"), volatility_30d=Decimal("0.07"))
    )
    assert sig.icon == "☁️"
    assert sig.weather == "cloudy"


def test_signal_stormy() -> None:
    sig = svc.generate_signal(
        _ctx(action="HOLD", utilization_rate=Decimal("0.65"), volatility_30d=Decimal("0.12"))
    )
    assert sig.icon == "🌪️"
    assert sig.weather == "stormy"


def test_signal_sell_stormy() -> None:
    sig = svc.generate_signal(_ctx(action="SELL"))
    assert sig.icon == "🌪️"
    assert sig.weather == "stormy"
