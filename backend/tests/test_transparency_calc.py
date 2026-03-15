from decimal import Decimal

from app.aave.impact_calculator import ImpactCalculator, ImpactParams
from app.aave.risk_profile import RiskProfileManager
from app.aave.safety_score import SafetyScoreCalculator, SafetyScoreParams
from app.aave.simulation_service import SimulationParams, SimulationService

# ─── SafetyScore ────────────────────────────────────────────────────────────


class TestSafetyScoreCalculator:
    def setup_method(self) -> None:
        self.calc = SafetyScoreCalculator()

    def test_optimal_conditions(self) -> None:
        params = SafetyScoreParams(
            utilization_rate=Decimal("0.1"),
            health_factor=Decimal("3.0"),
            volatility_30d=Decimal("0.05"),
        )
        result = self.calc.calculate(params)
        assert result.score >= Decimal("90")
        assert result.color == "green"

    def test_dangerous_conditions(self) -> None:
        params = SafetyScoreParams(
            utilization_rate=Decimal("0.95"),
            health_factor=Decimal("1.1"),
            volatility_30d=Decimal("0.8"),
        )
        result = self.calc.calculate(params)
        assert result.score < Decimal("30")
        assert result.color == "red"

    def test_no_position(self) -> None:
        params = SafetyScoreParams(
            utilization_rate=Decimal("0.5"),
            health_factor=Decimal("0"),  # no position
            volatility_30d=Decimal("0.2"),
        )
        result = self.calc.calculate(params)
        # HF score should be 50 (neutral)
        assert result.breakdown.hf_score == Decimal("50.00")

    def test_label_japanese(self) -> None:
        params = SafetyScoreParams(
            utilization_rate=Decimal("0.3"),
            health_factor=Decimal("2.5"),
            volatility_30d=Decimal("0.1"),
        )
        result = self.calc.calculate(params)
        assert result.label in ["とても安全", "安全", "注意", "警戒", "危険"]

    def test_all_decimal(self) -> None:
        params = SafetyScoreParams(
            utilization_rate=Decimal("0.5"),
            health_factor=Decimal("2.0"),
            volatility_30d=Decimal("0.3"),
        )
        result = self.calc.calculate(params)
        assert isinstance(result.score, Decimal)
        assert isinstance(result.breakdown.util_score, Decimal)
        assert isinstance(result.breakdown.hf_score, Decimal)
        assert isinstance(result.breakdown.vol_score, Decimal)


# ─── ImpactCalculator ───────────────────────────────────────────────────────


class TestImpactCalculator:
    def setup_method(self) -> None:
        self.calc = ImpactCalculator()

    def test_format_jpy(self) -> None:
        params = ImpactParams(
            current_balance_usd=Decimal("10000"),
            current_apy=Decimal("0.03"),
            proposed_apy=Decimal("0.06"),
            action_amount_usd=Decimal("5000"),
            days=30,
        )
        result = self.calc.calculate_impact(params)
        formatted = self.calc.format_comparison(result)
        assert isinstance(formatted.net_difference_jpy, Decimal)
        assert formatted.metaphor in ["自販機", "コーヒー", "ランチ", "ディナー"]

    def test_all_decimal(self) -> None:
        params = ImpactParams(
            current_balance_usd=Decimal("1000"),
            current_apy=Decimal("0.04"),
            proposed_apy=Decimal("0.05"),
            action_amount_usd=Decimal("0"),
            days=30,
        )
        result = self.calc.calculate_impact(params)
        assert isinstance(result.gain_with_action_usd, Decimal)
        assert isinstance(result.gain_without_action_usd, Decimal)
        assert isinstance(result.net_difference_usd, Decimal)


# ─── SimulationService ──────────────────────────────────────────────────────


class TestSimulationService:
    def setup_method(self) -> None:
        self.svc = SimulationService()

    def _params(self) -> SimulationParams:
        return SimulationParams(
            current_balance_usd=Decimal("10000"),
            current_apy=Decimal("0.04"),
            proposed_apy=Decimal("0.07"),
            additional_amount_usd=Decimal("3000"),
            gas_cost_usd=Decimal("5"),
            days=30,
        )

    def test_three_scenarios(self) -> None:
        result = self.svc.simulate(self._params())
        names = [s.name for s in result.scenarios]
        assert set(names) == {"supply", "withdraw", "hold"}

    def test_best_scenario(self) -> None:
        result = self.svc.simulate(self._params())
        assert result.best_scenario in {"supply", "withdraw", "hold"}
        best = next(s for s in result.scenarios if s.name == result.best_scenario)
        for s in result.scenarios:
            assert best.projected_gain_usd >= s.projected_gain_usd

    def test_disclaimer_always(self) -> None:
        result = self.svc.simulate(self._params())
        assert len(result.disclaimer) > 0


# ─── RiskProfileManager ─────────────────────────────────────────────────────


class TestRiskProfileManager:
    def setup_method(self) -> None:
        self.mgr = RiskProfileManager()

    def test_conservative_default(self) -> None:
        profile = self.mgr.get_profile("invalid_mode")
        assert profile.mode == "conservative"

    def test_blocks_eth_conservative(self) -> None:
        result = self.mgr.is_action_allowed("conservative", "ETH", Decimal("0.9"))
        assert result.allowed is False

    def test_allows_eth_balanced(self) -> None:
        result = self.mgr.is_action_allowed("balanced", "ETH", Decimal("0.8"))
        assert result.allowed is True

    def test_low_confidence_blocked(self) -> None:
        result = self.mgr.is_action_allowed("balanced", "USDC", Decimal("0.5"))
        assert result.allowed is False

    def test_invalid_mode_fallback(self) -> None:
        profile = self.mgr.get_profile("nonexistent")
        assert profile.mode == "conservative"
        assert profile.max_utilization == Decimal("0.6")
