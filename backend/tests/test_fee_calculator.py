# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_fee_calculator.py
"""F-5: ``backend/app/fees/calculator.py`` ユニットテスト。

5 収益ロジックの境界値・回帰・Decimal 精度を網羅する。
DB 接続は不要 (純粋関数 + factory による DB 未保存 instance)。

関連:
- backend/app/fees/calculator.py
- backend/tests/helpers/fee_config_factory.py
- docs/45_fee_model_v10_migration_plan.md §4 F-5 行
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-fee-calculator")

from app.auth.models import InvestmentTier, RiskMode  # noqa: E402
from app.fees import FeeCalculationInput, FeeCalculationResult, FeeCalculator  # noqa: E402
from app.fees.trade_gate import calculate_fee_by_market  # noqa: E402
from tests.helpers.fee_config_factory import make_v10_default_config  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def calculator() -> FeeCalculator:
    """v10_default 設定の FeeCalculator (DB 未保存 config)。"""
    return FeeCalculator(make_v10_default_config())


def _make_input(
    *,
    deposit: Decimal = Decimal("100000"),
    gross: Decimal = Decimal("0"),
    expense: Decimal = Decimal("0"),
    tier: InvestmentTier = InvestmentTier.LOWER,
    risk: RiskMode = RiskMode.CONSERVATIVE,
    affiliate_id: int | None = None,
    is_first_month: bool = False,
    user_id: int = 1,
) -> FeeCalculationInput:
    return FeeCalculationInput(
        user_id=user_id,
        calculation_month=date(2026, 5, 1),
        deposit_jpy=deposit,
        gross_profit_jpy=gross,
        expense_jpy=expense,
        user_tier=tier,
        user_risk_mode=risk,
        affiliate_id=affiliate_id,
        is_first_month=is_first_month,
    )


# ---------------------------------------------------------------------------
# Class 1: Basic 5-step flow
# ---------------------------------------------------------------------------


class TestBasicCalculation:
    """通常ケース (保護も cap もかからない) の 5 step を確認する。"""

    def test_lower_conservative_normal(self, calculator: FeeCalculator) -> None:
        # deposit 100,000円, 利益 1,000円, 経費 100円
        # net = 900, sub = 0 (conservative), fee = (900-0) * 0.30 = 270
        # provisional = 900 - 0 - 270 = 630, cap = 100000 * 0.018 = 1800
        # provisional <= cap → takehome = 630
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("1000"), expense=Decimal("100"))
        )
        assert result.net_profit_jpy == Decimal("900")
        assert result.subscription_amount_jpy == Decimal("0")
        assert result.fee_rate_applied == Decimal("0.30")
        assert result.fee_amount_jpy == Decimal("270")
        assert result.user_takehome_jpy == Decimal("630")
        assert result.yield_excess_to_uata_jpy == Decimal("0")
        assert result.subscription_protected is False
        assert result.affiliate_amount_jpy == Decimal("0")

    def test_middle_balanced_subscription_active(self, calculator: FeeCalculator) -> None:
        # deposit 1,000,000円, balanced (sub 0.3% = 3000), 利益 100,000, 経費 0
        # net = 100000, sub = 1000000 * 0.003 = 3000
        # fee = (100000 - 3000) * 0.25 = 24250
        # provisional = 100000 - 3000 - 24250 = 72750
        # cap = 1000000 * 0.023 = 23000
        # provisional > cap → takehome = 23000, excess = 49750
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("100000"),
                tier=InvestmentTier.MIDDLE,
                risk=RiskMode.BALANCED,
            )
        )
        assert result.subscription_amount_jpy == Decimal("3000")
        assert result.subscription_rate_applied == Decimal("0.003")
        assert result.fee_rate_applied == Decimal("0.25")
        assert result.fee_amount_jpy == Decimal("24250")
        assert result.user_takehome_jpy == Decimal("23000")
        assert result.yield_excess_to_uata_jpy == Decimal("49750")

    def test_upper_aggressive_full_pipeline(self, calculator: FeeCalculator) -> None:
        # deposit 10,000,000, aggressive (sub 1% = 100000), 利益 500,000, 経費 0
        # net = 500000, sub = 100000
        # fee = (500000 - 100000) * 0.20 = 80000
        # provisional = 500000 - 100000 - 80000 = 320000
        # cap = 10000000 * 0.030 = 300000
        # provisional > cap → takehome = 300000, excess = 20000
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("10000000"),
                gross=Decimal("500000"),
                tier=InvestmentTier.UPPER,
                risk=RiskMode.AGGRESSIVE,
            )
        )
        assert result.subscription_amount_jpy == Decimal("100000")
        assert result.fee_amount_jpy == Decimal("80000")
        assert result.user_takehome_jpy == Decimal("300000")
        assert result.yield_excess_to_uata_jpy == Decimal("20000")

    def test_first_month_subscription_zero(self, calculator: FeeCalculator) -> None:
        # is_first_month=True なら balanced でも sub=0
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("10000"),
                risk=RiskMode.BALANCED,
                is_first_month=True,
            )
        )
        assert result.subscription_rate_applied == Decimal("0")
        assert result.subscription_amount_jpy == Decimal("0")

    def test_zero_profit_and_zero_subscription(self, calculator: FeeCalculator) -> None:
        # 利益 0, conservative (sub=0) → 全て 0
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("0"), expense=Decimal("0"))
        )
        assert result.net_profit_jpy == Decimal("0")
        assert result.subscription_amount_jpy == Decimal("0")
        assert result.fee_amount_jpy == Decimal("0")
        assert result.user_takehome_jpy == Decimal("0")
        assert result.yield_excess_to_uata_jpy == Decimal("0")
        assert result.subscription_protected is False


# ---------------------------------------------------------------------------
# Class 2: Subscription Protection
# ---------------------------------------------------------------------------


class TestSubscriptionProtection:
    """net_profit < subscription なら全額 UATa、fee/affiliate 0、takehome 0。"""

    def test_protected_when_net_below_subscription(self, calculator: FeeCalculator) -> None:
        # balanced, deposit 1,000,000 → sub = 3000
        # 利益 1,000 (< 3000) → 保護発動
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("1000"),
                risk=RiskMode.BALANCED,
            )
        )
        assert result.subscription_protected is True
        assert result.subscription_amount_jpy == Decimal("0")
        assert result.fee_amount_jpy == Decimal("0")
        assert result.user_takehome_jpy == Decimal("0")
        assert result.yield_excess_to_uata_jpy == Decimal("1000")  # net 全額

    def test_boundary_net_equals_subscription_no_protection(
        self, calculator: FeeCalculator
    ) -> None:
        # net_profit == sub_amount のとき、`net < sub` は False なので保護発動しない
        # balanced sub = 1000000 * 0.003 = 3000, gross=3000 → net=3000
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("3000"),
                risk=RiskMode.BALANCED,
            )
        )
        assert result.subscription_protected is False
        assert result.subscription_amount_jpy == Decimal("3000")
        # fee_base = 3000 - 3000 = 0 → fee = 0
        assert result.fee_amount_jpy == Decimal("0")

    def test_protected_on_loss_with_subscription(self, calculator: FeeCalculator) -> None:
        # 損失 (net < 0), sub > 0 → 保護発動
        # balanced, deposit 1,000,000 → sub = 3000
        # net = -500 (gross 500 - expense 1000)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("500"),
                expense=Decimal("1000"),
                risk=RiskMode.BALANCED,
            )
        )
        assert result.subscription_protected is True
        assert result.net_profit_jpy == Decimal("-500")
        assert result.yield_excess_to_uata_jpy == Decimal("-500")  # 負の値もそのまま UATa
        assert result.fee_amount_jpy == Decimal("0")
        assert result.affiliate_amount_jpy == Decimal("0")

    def test_no_protection_when_subscription_zero(self, calculator: FeeCalculator) -> None:
        # conservative (sub=0) では保護発動条件 (sub > 0) を満たさない
        # gross=100, expense=200 → net=-100 でもそのまま (保護なし)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("100"),
                expense=Decimal("200"),
                risk=RiskMode.CONSERVATIVE,
            )
        )
        assert result.subscription_protected is False
        assert result.net_profit_jpy == Decimal("-100")
        # fee_base = -100 < 0 → fee = 0
        assert result.fee_amount_jpy == Decimal("0")
        # provisional = -100, cap = 18000, -100 <= 18000 → takehome = -100 (損失そのまま)
        assert result.user_takehome_jpy == Decimal("-100")


# ---------------------------------------------------------------------------
# Class 3: Monthly Yield Cap
# ---------------------------------------------------------------------------


class TestMonthlyYieldCap:
    """provisional_takehome > cap_amount なら excess を UATa に回す。"""

    def test_lower_cap_applied(self, calculator: FeeCalculator) -> None:
        # LOWER: cap = deposit * 0.018
        # deposit 100000 → cap = 1800
        # conservative (sub=0), gross=10000 → net=10000
        # fee = 10000 * 0.30 = 3000
        # provisional = 10000 - 0 - 3000 = 7000
        # 7000 > 1800 → takehome=1800, excess=5200
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("10000"))
        )
        assert result.monthly_yield_cap_applied == Decimal("0.018")
        assert result.user_takehome_jpy == Decimal("1800")
        assert result.yield_excess_to_uata_jpy == Decimal("5200")

    def test_middle_cap_applied(self, calculator: FeeCalculator) -> None:
        # MIDDLE: cap = deposit * 0.023
        # deposit 1000000 → cap = 23000
        # conservative (sub=0), gross=200000 → net=200000
        # fee = 200000 * 0.25 = 50000
        # provisional = 200000 - 0 - 50000 = 150000
        # 150000 > 23000 → takehome=23000, excess=127000
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("200000"),
                tier=InvestmentTier.MIDDLE,
            )
        )
        assert result.monthly_yield_cap_applied == Decimal("0.023")
        assert result.user_takehome_jpy == Decimal("23000")
        assert result.yield_excess_to_uata_jpy == Decimal("127000")

    def test_upper_cap_applied(self, calculator: FeeCalculator) -> None:
        # UPPER: cap = deposit * 0.030
        # cap = 10000000 * 0.030 = 300000
        # net = 1000000, fee = 1000000 * 0.20 = 200000
        # provisional = 1000000 - 0 - 200000 = 800000
        # 800000 > 300000 → takehome=300000, excess=500000
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("10000000"),
                gross=Decimal("1000000"),
                tier=InvestmentTier.UPPER,
            )
        )
        assert result.monthly_yield_cap_applied == Decimal("0.030")
        assert result.user_takehome_jpy == Decimal("300000")
        assert result.yield_excess_to_uata_jpy == Decimal("500000")

    def test_boundary_provisional_equals_cap(self, calculator: FeeCalculator) -> None:
        # provisional == cap のとき、`provisional > cap` は False なので excess 発動しない
        # LOWER: cap=1800. fee_rate=0.30 → provisional=net*0.7
        # net=2571 → fee=2571*0.30=771.3→ROUND_DOWN→771, provisional=2571-771=1800 (= cap)
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("2571"))
        )
        assert result.user_takehome_jpy == Decimal("1800")
        assert result.yield_excess_to_uata_jpy == Decimal("0")


# ---------------------------------------------------------------------------
# Class 4: Affiliate
# ---------------------------------------------------------------------------


class TestAffiliate:
    """affiliate_id あり + sub > 0 で 30% 発動。"""

    def test_affiliate_when_subscription_active(self, calculator: FeeCalculator) -> None:
        # balanced, deposit 1000000 → sub = 3000
        # affiliate = 3000 * 0.30 = 900
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("10000"),
                risk=RiskMode.BALANCED,
                affiliate_id=99,
            )
        )
        assert result.affiliate_id == 99
        assert result.affiliate_amount_jpy == Decimal("900")

    def test_affiliate_skipped_when_subscription_zero(self, calculator: FeeCalculator) -> None:
        # conservative (sub=0) では affiliate 発動しない
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("10000"),
                risk=RiskMode.CONSERVATIVE,
                affiliate_id=99,
            )
        )
        assert result.affiliate_id is None
        assert result.affiliate_amount_jpy == Decimal("0")

    def test_no_affiliate_when_id_none(self, calculator: FeeCalculator) -> None:
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("10000"),
                risk=RiskMode.BALANCED,
                affiliate_id=None,
            )
        )
        assert result.affiliate_id is None
        assert result.affiliate_amount_jpy == Decimal("0")


# ---------------------------------------------------------------------------
# Class 5: Decimal Precision (no float, ROUND_DOWN)
# ---------------------------------------------------------------------------


class TestDecimalPrecision:
    """全ての金額が Decimal、float 混入なし、円未満切り捨て。"""

    def test_all_amount_fields_are_decimal(self, calculator: FeeCalculator) -> None:
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("100000"),
                tier=InvestmentTier.MIDDLE,
                risk=RiskMode.BALANCED,
                affiliate_id=99,
            )
        )
        decimal_fields = (
            result.deposit_jpy,
            result.gross_profit_jpy,
            result.expense_jpy,
            result.net_profit_jpy,
            result.fee_rate_applied,
            result.fee_amount_jpy,
            result.subscription_rate_applied,
            result.subscription_amount_jpy,
            result.monthly_yield_cap_applied,
            result.yield_excess_to_uata_jpy,
            result.user_takehome_jpy,
            result.affiliate_amount_jpy,
        )
        for v in decimal_fields:
            assert isinstance(v, Decimal), f"Got {type(v).__name__} (expected Decimal)"

    def test_round_jpy_truncates_positive(self) -> None:
        assert FeeCalculator._round_jpy(Decimal("1234.56")) == Decimal("1234")
        assert FeeCalculator._round_jpy(Decimal("1234.99")) == Decimal("1234")

    def test_round_jpy_truncates_negative_toward_zero(self) -> None:
        # ROUND_DOWN は 0 方向に丸める。-1234.56 → -1234 (ROUND_FLOOR の -1235 ではない)。
        assert FeeCalculator._round_jpy(Decimal("-1234.56")) == Decimal("-1234")
        assert FeeCalculator._round_jpy(Decimal("-1234.01")) == Decimal("-1234")

    def test_subscription_amount_truncates_fractional(self, calculator: FeeCalculator) -> None:
        # deposit 100,001 * 0.003 = 300.003 → 300 (端数切り捨て)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100001"),
                gross=Decimal("100000"),
                risk=RiskMode.BALANCED,
            )
        )
        assert result.subscription_amount_jpy == Decimal("300")

    def test_fee_amount_truncates_fractional(self, calculator: FeeCalculator) -> None:
        # net = 333, fee_rate = 0.30 → 333 * 0.30 = 99.9 → 99
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("333"))
        )
        assert result.fee_amount_jpy == Decimal("99")


# ---------------------------------------------------------------------------
# Class 6: Regression — coexistence with dynamic_fee
# ---------------------------------------------------------------------------


class TestTradeGate:
    """§4 トレードゲート: 予想利益 > 経費 のみを判定。手数料は月次バッチで計算。"""

    def test_gate_passes_when_profit_exceeds_cost(self) -> None:
        # net_profit = 100 - 0.27 = 99.73 > 0 → should_trade=True
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("10000"),
            tier="GENERAL",
            current_apy=Decimal("2"),
            expected_profit_usd=Decimal("100"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True
        # per-trade fee は常に 0 (月次バッチで計算)
        assert result.fee_rate == Decimal("0")
        assert result.fee_amount == Decimal("0")

    def test_gate_blocks_when_profit_equals_cost(self) -> None:
        # net_profit = 0.27 - 0.27 = 0 → should_trade=False
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("10000"),
            tier="LOWER",
            current_apy=Decimal("2"),
            expected_profit_usd=Decimal("0.27"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is False

    def test_gate_blocks_when_profit_below_cost(self) -> None:
        # net_profit = 0.10 - 0.27 = -0.17 ≤ 0 → should_trade=False
        result = calculate_fee_by_market(
            trade_amount_usd=Decimal("100"),
            tier="LOWER",
            current_apy=Decimal("2"),
            expected_profit_usd=Decimal("0.10"),
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is False

    def test_all_tiers_return_zero_fee(self) -> None:
        """tier に関わらず per-trade fee は 0 (月次バッチで計算)。"""
        for tier in ("LOWER", "MIDDLE", "UPPER", "GENERAL"):
            result = calculate_fee_by_market(
                trade_amount_usd=Decimal("10000"),
                tier=tier,
                current_apy=Decimal("5"),
                expected_profit_usd=Decimal("100"),
            )
            assert result.fee_rate == Decimal("0"), f"tier={tier} で fee_rate != 0"
            assert result.fee_amount == Decimal("0"), f"tier={tier} で fee_amount != 0"

    def test_f5_and_trade_gate_coexist(self) -> None:
        """F-5 月次計算と §4 トレードゲートが独立して動作すること。"""
        calculator = FeeCalculator(make_v10_default_config())
        for tier in (InvestmentTier.LOWER, InvestmentTier.MIDDLE, InvestmentTier.UPPER):
            monthly_result: FeeCalculationResult = calculator.calculate_monthly(
                _make_input(deposit=Decimal("100000"), gross=Decimal("1000"), tier=tier)
            )
            gate_result = calculate_fee_by_market(
                trade_amount_usd=Decimal("10000"),
                tier=monthly_result.tier,
                current_apy=Decimal("5"),
                expected_profit_usd=Decimal("100"),
            )
            # 月次計算は tier 別手数料を計算する
            assert monthly_result.fee_rate_applied > Decimal("0")
            # per-trade ゲートは手数料 0 を返す
            assert gate_result.fee_rate == Decimal("0")


# ---------------------------------------------------------------------------
# Class 7: GENERAL tier (deprecated) handling
# ---------------------------------------------------------------------------


class TestGeneralTierLegacyHandling:
    """GENERAL は LOWER と同等扱い (F-2 LEGACY_TIER_MAP 方針)。"""

    def test_general_tier_normalized_to_lower_in_output(self, calculator: FeeCalculator) -> None:
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("1000"),
                tier=InvestmentTier.GENERAL,
            )
        )
        # tier フィールドは "LOWER" に正規化される (CHECK 制約準拠)
        assert result.tier == "LOWER"

    def test_general_tier_uses_lower_fee_rate(self, calculator: FeeCalculator) -> None:
        # GENERAL → tier_fee_rates[0] = 0.30 (LOWER と同じ)
        result_general = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("1000"),
                tier=InvestmentTier.GENERAL,
            )
        )
        result_lower = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("1000"))
        )
        assert result_general.fee_rate_applied == result_lower.fee_rate_applied
        assert result_general.fee_amount_jpy == result_lower.fee_amount_jpy
        assert result_general.user_takehome_jpy == result_lower.user_takehome_jpy


# ---------------------------------------------------------------------------
# Class 8: Debug log
# ---------------------------------------------------------------------------


class TestDebugLog:
    """debug_log に各 step の計算過程が記録される。"""

    def test_debug_log_contains_all_steps_normal(self, calculator: FeeCalculator) -> None:
        result = calculator.calculate_monthly(
            _make_input(deposit=Decimal("100000"), gross=Decimal("1000"))
        )
        joined = "\n".join(result.debug_log)
        for step in ("step1", "step2", "step4", "step5", "step6"):
            assert step in joined

    def test_debug_log_marks_subscription_protection(self, calculator: FeeCalculator) -> None:
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("100"),
                risk=RiskMode.BALANCED,
            )
        )
        joined = "\n".join(result.debug_log)
        assert "SUBSCRIPTION_PROTECTED" in joined


# ---------------------------------------------------------------------------
# Class 9: Expense Markup (F-9)
# ---------------------------------------------------------------------------


class TestExpenseMarkup:
    """Step 0: expense_markup 適用 (F-9) の境界値テスト。

    デフォルト OFF (expense_markup_enabled=False) 前提を検証し、
    ON 時のマークアップ計算・保護判定への影響・Decimal 精度を網羅する。
    """

    def test_markup_disabled_default(self) -> None:
        """既定 (expense_markup_enabled=False) でマークアップなし。"""
        calculator = FeeCalculator(make_v10_default_config())
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("5000"),
                expense=Decimal("1000"),
            )
        )
        assert result.expense_markup_rate_applied == Decimal("0")
        assert result.expense_markup_amount_jpy == Decimal("0")
        assert result.raw_expense_jpy == Decimal("1000")
        assert result.expense_jpy == Decimal("1000")
        assert result.net_profit_jpy == Decimal("4000")

    def test_markup_10_percent(self) -> None:
        """expense_markup_rate=0.10 で実費 × 1.10 が課金対象。

        expense=1000, rate=0.10 → effective=1100, markup_amount=100
        net = 10000 - 1100 = 8900
        """
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0.10")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("10000"),
                expense=Decimal("1000"),
            )
        )
        assert result.raw_expense_jpy == Decimal("1000")
        assert result.expense_markup_rate_applied == Decimal("0.10")
        assert result.expense_jpy == Decimal("1100")
        assert result.expense_markup_amount_jpy == Decimal("100")
        assert result.net_profit_jpy == Decimal("8900")

    def test_markup_zero_rate_with_enabled_true_is_noop(self) -> None:
        """enabled=True でも rate=0 なら markup_amount=0 (加算ゼロ)。"""
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("5000"),
                expense=Decimal("1000"),
            )
        )
        assert result.expense_markup_rate_applied == Decimal("0")
        assert result.expense_markup_amount_jpy == Decimal("0")
        assert result.expense_jpy == Decimal("1000")
        assert result.raw_expense_jpy == Decimal("1000")

    def test_markup_with_subscription_protection(self) -> None:
        """マークアップ適用後の net_profit がサブスク保護判定に使われること。

        raw_expense=900, markup=0.20 → effective=1080
        gross=2000, deposit=1_000_000, balanced (sub=3000)
        net = 2000 - 1080 = 920 < sub(3000) → 保護発動
        """
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0.20")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("1000000"),
                gross=Decimal("2000"),
                expense=Decimal("900"),
                risk=RiskMode.BALANCED,
            )
        )
        assert result.raw_expense_jpy == Decimal("900")
        assert result.expense_jpy == Decimal("1080")
        assert result.expense_markup_amount_jpy == Decimal("180")
        assert result.net_profit_jpy == Decimal("920")
        assert result.subscription_protected is True
        assert result.fee_amount_jpy == Decimal("0")
        assert result.user_takehome_jpy == Decimal("0")

    def test_markup_decimal_precision(self) -> None:
        """マークアップ計算でも円未満切り捨て (ROUND_DOWN)。

        expense=333, rate=0.07 → 333*1.07=356.31 → 356
        markup_amount = 356 - 333 = 23
        """
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0.07")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("10000"),
                expense=Decimal("333"),
            )
        )
        assert result.raw_expense_jpy == Decimal("333")
        assert result.expense_jpy == Decimal("356")
        assert result.expense_markup_amount_jpy == Decimal("23")
        assert result.net_profit_jpy == Decimal("9644")

    def test_markup_with_yield_cap(self) -> None:
        """マークアップで net_profit が減少し yield_cap の計算に影響すること。

        deposit=100000, LOWER cap=0.018 → cap=1800
        expense=500, rate=0.20 → effective=600
        net = 10000 - 600 = 9400
        fee = 9400 * 0.30 = 2820
        provisional = 6580 > cap(1800) → takehome=1800, excess=4780
        """
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0.20")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("10000"),
                expense=Decimal("500"),
            )
        )
        assert result.expense_jpy == Decimal("600")
        assert result.net_profit_jpy == Decimal("9400")
        assert result.fee_amount_jpy == Decimal("2820")
        assert result.user_takehome_jpy == Decimal("1800")
        assert result.yield_excess_to_uata_jpy == Decimal("4780")

    def test_markup_new_fields_are_decimal_type(self) -> None:
        """F-9 追加フィールドが全て Decimal 型であること。"""
        config = make_v10_default_config()
        config.expense_markup_enabled = True
        config.expense_markup_rate = Decimal("0.15")
        calculator = FeeCalculator(config)
        result = calculator.calculate_monthly(
            _make_input(
                deposit=Decimal("100000"),
                gross=Decimal("5000"),
                expense=Decimal("500"),
            )
        )
        for field_name, value in [
            ("raw_expense_jpy", result.raw_expense_jpy),
            ("expense_markup_rate_applied", result.expense_markup_rate_applied),
            ("expense_markup_amount_jpy", result.expense_markup_amount_jpy),
        ]:
            assert isinstance(value, Decimal), (
                f"{field_name}: got {type(value).__name__} (expected Decimal)"
            )
