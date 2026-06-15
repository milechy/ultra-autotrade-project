# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
x402 純粋バリデータ テスト群 (Phase 0 scaffold)

設計方針:
  - 外部I/O・blockchain・HTTP に依存しない純粋関数のみテスト
  - 全金額は Decimal (float 禁止 / Security Rules 11)
  - Decimal 境界値 (= 上限ちょうど / +0.01 超過) を必ずテスト
  - workflow.py の daily_limit_reached 相当の挙動を確認
"""

from decimal import Decimal

import pytest

from app.data_feeds.x402.schemas import (
    X402BudgetPolicy,
    X402PaymentToken,
    X402PurchaseIntent,
)
from app.data_feeds.x402.validators import (
    validate_amount_positive,
    validate_purchase_intent,
    validate_token_allowed,
    validate_within_daily_budget,
    validate_within_per_request_limit,
)

# ===== フィクスチャ =====


@pytest.fixture
def basic_policy() -> X402BudgetPolicy:
    """基本テスト用予算ポリシー。"""
    return X402BudgetPolicy(
        max_per_request_usd=Decimal("5.00"),
        daily_budget_usd=Decimal("20.00"),
    )


@pytest.fixture
def basic_intent() -> X402PurchaseIntent:
    """基本テスト用購入意図。"""
    return X402PurchaseIntent(
        resource_url="https://api.example.com/v1/premium-sentiment",
        amount_usd=Decimal("1.00"),
        token=X402PaymentToken.USDC,
        description="AI判断用プレミアム感情分析データ",
    )


@pytest.fixture
def allowed_tokens() -> set[X402PaymentToken]:
    """許可トークン集合 (USDC のみ)。"""
    return {X402PaymentToken.USDC}


# ===== validate_amount_positive =====


class TestValidateAmountPositive:
    def test_positive_amount_passes(self, basic_intent: X402PurchaseIntent) -> None:
        """正の金額は通過する。"""
        basic_intent.amount_usd = Decimal("0.01")
        validate_amount_positive(basic_intent)  # 例外なし

    def test_zero_amount_raises(self, basic_intent: X402PurchaseIntent) -> None:
        """0 は拒否される。"""
        basic_intent.amount_usd = Decimal("0")
        with pytest.raises(ValueError, match="正の値である必要があります"):
            validate_amount_positive(basic_intent)

    def test_negative_amount_raises(self, basic_intent: X402PurchaseIntent) -> None:
        """負の値は拒否される。"""
        basic_intent.amount_usd = Decimal("-1.00")
        with pytest.raises(ValueError, match="正の値である必要があります"):
            validate_amount_positive(basic_intent)

    def test_very_small_positive_passes(self, basic_intent: X402PurchaseIntent) -> None:
        """Decimal 最小正値は通過する。"""
        basic_intent.amount_usd = Decimal("0.000001")
        validate_amount_positive(basic_intent)  # 例外なし


# ===== validate_within_per_request_limit =====


class TestValidateWithinPerRequestLimit:
    def test_exactly_at_limit_passes(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """上限ちょうど (= max_per_request_usd) は通過する (境界値)。"""
        basic_intent.amount_usd = Decimal("5.00")
        validate_within_per_request_limit(basic_intent, basic_policy)  # 例外なし

    def test_one_cent_over_limit_raises(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """上限 + 0.01 は拒否される (境界値 + 1)。"""
        basic_intent.amount_usd = Decimal("5.01")
        with pytest.raises(ValueError, match="1リクエスト上限"):
            validate_within_per_request_limit(basic_intent, basic_policy)

    def test_well_under_limit_passes(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """上限未満は通過する。"""
        basic_intent.amount_usd = Decimal("1.00")
        validate_within_per_request_limit(basic_intent, basic_policy)  # 例外なし


# ===== validate_within_daily_budget =====


class TestValidateWithinDailyBudget:
    def test_exactly_at_daily_limit_passes(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """累積 + 今回 = daily_budget_usd ちょうどは通過する (境界値)。"""
        basic_intent.amount_usd = Decimal("5.00")
        spent = Decimal("15.00")  # 15 + 5 = 20 = daily_budget_usd
        validate_within_daily_budget(basic_intent, basic_policy, spent)  # 例外なし

    def test_one_cent_over_daily_limit_raises(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """累積 + 今回 が daily_budget_usd + 0.01 は拒否される (境界値 + 1)。"""
        basic_intent.amount_usd = Decimal("5.01")
        spent = Decimal("15.00")  # 15 + 5.01 = 20.01 > 20
        with pytest.raises(ValueError, match="日次予算上限超過"):
            validate_within_daily_budget(basic_intent, basic_policy, spent)

    def test_zero_spent_passes(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """累積 0 で小額購入は通過する。"""
        basic_intent.amount_usd = Decimal("1.00")
        validate_within_daily_budget(basic_intent, basic_policy, Decimal("0"))

    def test_already_at_limit_raises(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """累積が既に daily_budget_usd 上限に達している場合は拒否 (workflow.py daily_limit_reached 相当)。"""
        basic_intent.amount_usd = Decimal("0.01")
        spent = Decimal("20.00")  # already at limit
        with pytest.raises(ValueError, match="日次予算上限超過"):
            validate_within_daily_budget(basic_intent, basic_policy, spent)

    def test_decimal_accumulation_precision(
        self, basic_intent: X402PurchaseIntent, basic_policy: X402BudgetPolicy
    ) -> None:
        """Decimal 累積計算の精度: 0.1 * 200 回の積み上げが 20.0 = 境界値 (float なら誤差発生)。"""
        # float だと 0.1 * 200 は厳密に 20.0 にならない可能性があるが Decimal は正確
        basic_intent.amount_usd = Decimal("0.1")
        spent = sum([Decimal("0.1")] * 199, Decimal("0"))  # 0.1 * 199 = 19.9
        # 19.9 + 0.1 = 20.0 = daily_budget_usd ちょうど → 通過
        validate_within_daily_budget(basic_intent, basic_policy, spent)


# ===== validate_token_allowed =====


class TestValidateTokenAllowed:
    def test_allowed_token_passes(
        self,
        basic_intent: X402PurchaseIntent,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """許可トークンは通過する。"""
        basic_intent.token = X402PaymentToken.USDC
        validate_token_allowed(basic_intent, allowed_tokens)  # 例外なし

    def test_disallowed_token_raises(
        self,
        basic_intent: X402PurchaseIntent,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """許可集合外のトークンは拒否される。"""
        basic_intent.token = X402PaymentToken.USDT
        with pytest.raises(ValueError, match="許可されていません"):
            validate_token_allowed(basic_intent, allowed_tokens)

    def test_empty_allowed_set_raises(self, basic_intent: X402PurchaseIntent) -> None:
        """空の許可集合は全トークンを拒否する。"""
        with pytest.raises(ValueError, match="許可されていません"):
            validate_token_allowed(basic_intent, set())

    def test_multiple_allowed_tokens(self, basic_intent: X402PurchaseIntent) -> None:
        """複数許可トークンの場合、いずれかが含まれれば通過する。"""
        multi = {X402PaymentToken.USDC, X402PaymentToken.USDT}
        basic_intent.token = X402PaymentToken.USDT
        validate_token_allowed(basic_intent, multi)  # 例外なし


# ===== validate_purchase_intent (AND 集約) =====


class TestValidatePurchaseIntent:
    def test_all_valid_returns_true_none(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """正常系: 全バリデーション通過で (True, None) を返す。"""
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is True
        assert reason is None

    def test_zero_amount_returns_false_with_reason(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """amount_usd=0 は (False, reason) を返す。"""
        basic_intent.amount_usd = Decimal("0")
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is False
        assert reason is not None
        assert "正の値" in reason

    def test_over_per_request_limit_returns_false(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """1リクエスト上限超過は (False, reason) を返す。"""
        basic_intent.amount_usd = Decimal("999.99")
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is False
        assert reason is not None
        assert "1リクエスト上限" in reason

    def test_daily_budget_exceeded_returns_false(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """日次予算超過は (False, reason) を返す (workflow.py daily_limit_reached 相当)。"""
        basic_intent.amount_usd = Decimal("1.00")
        spent = Decimal("20.00")  # already at limit
        ok, reason = validate_purchase_intent(basic_intent, basic_policy, spent, allowed_tokens)
        assert ok is False
        assert reason is not None
        assert "日次予算上限超過" in reason

    def test_disallowed_token_returns_false(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """許可外トークンは (False, reason) を返す。"""
        basic_intent.token = X402PaymentToken.USDT
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is False
        assert reason is not None
        assert "許可されていません" in reason

    def test_boundary_exactly_at_per_request_limit_passes(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """境界値: max_per_request_usd ちょうどは通過する。"""
        basic_intent.amount_usd = Decimal("5.00")
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is True
        assert reason is None

    def test_boundary_one_cent_over_per_request_fails(
        self,
        basic_intent: X402PurchaseIntent,
        basic_policy: X402BudgetPolicy,
        allowed_tokens: set[X402PaymentToken],
    ) -> None:
        """境界値: max_per_request_usd + 0.01 は拒否される。"""
        basic_intent.amount_usd = Decimal("5.01")
        ok, reason = validate_purchase_intent(
            basic_intent, basic_policy, Decimal("0"), allowed_tokens
        )
        assert ok is False
        assert reason is not None
