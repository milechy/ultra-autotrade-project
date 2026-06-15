# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_wallet_policy.py
"""
WalletPolicySpec / バリデータ / 各ルールの pass/fail ユニットテスト。

Privy API 呼出なし・DB 不要・純粋関数テスト。
金融値 Decimal 型強制 (Rule 11) の境界値テストを含む。
"""

import os
from decimal import Decimal

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-wallet-policy")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.policy.wallet_policy import (  # noqa: E402
    ConditionalSignRule,
    SpendingLimitRule,
    WalletAllowlistRule,
    WalletPolicySpec,
    WalletPolicyValidationError,
    _coerce_decimal,
    make_allowlist_rule,
    make_spending_limit_rule,
    validate_wallet_policy_spec,
)

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

_VALID_WALLET = "0xabcdef1234567890abcdef1234567890abcdef12"
_VALID_CONTRACT = "0x1111111111111111111111111111111111111111"
_VALID_ASSET = "USDC"
_VALID_POLICY_ID = "policy-001"


def _valid_allowlist() -> WalletAllowlistRule:
    return make_allowlist_rule(
        allowed_contracts=[_VALID_CONTRACT],
        allowed_assets=[_VALID_ASSET],
    )


def _valid_spending_limit() -> SpendingLimitRule:
    return make_spending_limit_rule(
        per_transaction_usd=Decimal("1000"),
        per_day_usd=Decimal("5000"),
        per_week_usd=Decimal("20000"),
    )


def _valid_conditional_sign() -> ConditionalSignRule:
    return ConditionalSignRule(
        field_path="args.asset",
        operator="eq",
        value="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        description="USDC のみ許可",
    )


def _valid_spec(**overrides) -> WalletPolicySpec:
    defaults: dict = dict(
        wallet_address=_VALID_WALLET,
        policy_id=_VALID_POLICY_ID,
        allowlist=_valid_allowlist(),
        spending_limit=_valid_spending_limit(),
        conditional_signs=[],
    )
    defaults.update(overrides)
    return WalletPolicySpec(**defaults)


def _assert_violation_contains(spec: WalletPolicySpec, keyword: str) -> None:
    """バリデーション違反メッセージに keyword が含まれることを確認。"""
    with pytest.raises(WalletPolicyValidationError) as exc_info:
        validate_wallet_policy_spec(spec)
    messages = " ".join(exc_info.value.violations)
    assert keyword in messages, f"Expected '{keyword}' in violations: {exc_info.value.violations}"


# ---------------------------------------------------------------------------
# WalletAllowlistRule のテスト
# ---------------------------------------------------------------------------


class TestWalletAllowlistRule:
    def test_valid_allowlist_passes(self) -> None:
        rule = make_allowlist_rule(
            allowed_contracts=[_VALID_CONTRACT],
            allowed_assets=[_VALID_ASSET],
        )
        spec = _valid_spec(allowlist=rule, spending_limit=None)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_contract_address_normalized_to_lowercase(self) -> None:
        rule = make_allowlist_rule(
            allowed_contracts=["0xABCDEF1234567890ABCDEF1234567890ABCDEF12"],
            allowed_assets=["usdc"],
        )
        assert "0xabcdef1234567890abcdef1234567890abcdef12" in rule.allowed_contracts
        assert "USDC" in rule.allowed_assets

    def test_asset_normalized_to_uppercase(self) -> None:
        rule = make_allowlist_rule(
            allowed_contracts=[_VALID_CONTRACT],
            allowed_assets=["usdc", "weth"],
        )
        assert "USDC" in rule.allowed_assets
        assert "WETH" in rule.allowed_assets
        # 小文字は含まれない
        assert "usdc" not in rule.allowed_assets

    def test_empty_contracts_fails(self) -> None:
        rule = WalletAllowlistRule(
            allowed_contracts=frozenset(),
            allowed_assets=frozenset({_VALID_ASSET}),
        )
        spec = _valid_spec(allowlist=rule, spending_limit=None)
        _assert_violation_contains(spec, "allowed_contracts must not be empty")

    def test_empty_assets_fails(self) -> None:
        rule = WalletAllowlistRule(
            allowed_contracts=frozenset({_VALID_CONTRACT}),
            allowed_assets=frozenset(),
        )
        spec = _valid_spec(allowlist=rule, spending_limit=None)
        _assert_violation_contains(spec, "allowed_assets must not be empty")

    def test_invalid_contract_address_fails(self) -> None:
        rule = WalletAllowlistRule(
            allowed_contracts=frozenset({"not-an-address"}),
            allowed_assets=frozenset({_VALID_ASSET}),
        )
        spec = _valid_spec(allowlist=rule, spending_limit=None)
        _assert_violation_contains(spec, "invalid address")

    def test_multiple_contracts_allowed(self) -> None:
        rule = make_allowlist_rule(
            allowed_contracts=[_VALID_CONTRACT, "0x2222222222222222222222222222222222222222"],
            allowed_assets=[_VALID_ASSET, "WETH"],
        )
        spec = _valid_spec(allowlist=rule, spending_limit=None)
        validate_wallet_policy_spec(spec)  # 例外なし


# ---------------------------------------------------------------------------
# SpendingLimitRule のテスト
# ---------------------------------------------------------------------------


class TestSpendingLimitRule:
    def test_valid_spending_limit_passes(self) -> None:
        rule = make_spending_limit_rule(
            per_transaction_usd=Decimal("1000"),
            per_day_usd=Decimal("5000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_decimal_coercion_from_string(self) -> None:
        rule = make_spending_limit_rule(
            per_transaction_usd="1000",
            per_day_usd="5000",
        )
        assert isinstance(rule.per_transaction_usd, Decimal)
        assert isinstance(rule.per_day_usd, Decimal)
        assert rule.per_transaction_usd == Decimal("1000")

    def test_decimal_type_enforced_rule11(self) -> None:
        """Rule 11: float を直接渡した場合は型エラー (Decimal で包んでからオブジェクト生成)。"""
        # SpendingLimitRule は frozen dataclass のため float のまま入れると違反検出
        rule = SpendingLimitRule(
            per_transaction_usd=1000.0,  # type: ignore[arg-type]
            per_day_usd=5000.0,  # type: ignore[arg-type]
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        _assert_violation_contains(spec, "must be Decimal type")

    def test_zero_per_transaction_fails(self) -> None:
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("0"),
            per_day_usd=Decimal("5000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        _assert_violation_contains(spec, "must be positive")

    def test_negative_per_day_fails(self) -> None:
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("100"),
            per_day_usd=Decimal("-1"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        _assert_violation_contains(spec, "must be positive")

    def test_per_transaction_exceeds_per_day_fails(self) -> None:
        """単一 tx 上限が日次上限を超える矛盾。"""
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("6000"),
            per_day_usd=Decimal("5000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        _assert_violation_contains(spec, "per_transaction_usd")

    def test_per_day_exceeds_per_week_fails(self) -> None:
        """日次上限が週次上限を超える矛盾。"""
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("1000"),
            per_day_usd=Decimal("10000"),
            per_week_usd=Decimal("5000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        _assert_violation_contains(spec, "per_day_usd")

    def test_boundary_per_transaction_equals_per_day_passes(self) -> None:
        """単一 tx == 日次上限は許容 (1日1取引のみのポリシー)。"""
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("5000"),
            per_day_usd=Decimal("5000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_boundary_per_day_equals_per_week_passes(self) -> None:
        """日次 == 週次は許容。"""
        rule = SpendingLimitRule(
            per_transaction_usd=Decimal("1000"),
            per_day_usd=Decimal("7000"),
            per_week_usd=Decimal("7000"),
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_per_week_optional_none_passes(self) -> None:
        rule = make_spending_limit_rule(
            per_transaction_usd=Decimal("1000"),
            per_day_usd=Decimal("5000"),
            per_week_usd=None,
        )
        spec = _valid_spec(allowlist=None, spending_limit=rule)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_coerce_decimal_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot convert"):
            _coerce_decimal("not-a-number", "test_field")

    def test_coerce_decimal_passthrough_decimal(self) -> None:
        d = Decimal("123.45")
        assert _coerce_decimal(d, "test_field") is d


# ---------------------------------------------------------------------------
# ConditionalSignRule のテスト
# ---------------------------------------------------------------------------


class TestConditionalSignRule:
    def test_valid_eq_rule_passes(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="eq",
            value="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            description="USDC asset check",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_valid_in_rule_with_list_passes(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.operation",
            operator="in",
            value=["SUPPLY", "WITHDRAW"],
            description="SUPPLY または WITHDRAW のみ",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_empty_field_path_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="",
            operator="eq",
            value="foo",
            description="desc",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "field_path must not be empty")

    def test_invalid_operator_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="contains",  # type: ignore[arg-type]
            value="foo",
            description="desc",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "operator")

    def test_in_operator_requires_list_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="in",
            value="USDC",  # str ではなく list が必要
            description="desc",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "list[str]")

    def test_in_operator_empty_list_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="in",
            value=[],
            description="desc",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "must not be empty")

    def test_eq_operator_with_list_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="eq",
            value=["USDC"],  # eq は str が必要
            description="desc",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "must be str")

    def test_empty_description_fails(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="eq",
            value="USDC",
            description="",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        _assert_violation_contains(spec, "description must not be empty")

    def test_all_scalar_operators_pass(self) -> None:
        for op in ["eq", "neq", "gt", "lt", "gte", "lte"]:
            rule = ConditionalSignRule(
                field_path="args.amount",
                operator=op,  # type: ignore[arg-type]
                value="100",
                description=f"{op} check",
            )
            spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
            validate_wallet_policy_spec(spec)  # 例外なし

    def test_not_in_operator_passes(self) -> None:
        rule = ConditionalSignRule(
            field_path="args.asset",
            operator="not_in",
            value=["DAI", "USDT"],
            description="DAI と USDT を除外",
        )
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[rule])
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_multiple_conditional_signs_pass(self) -> None:
        rules = [
            ConditionalSignRule("args.asset", "eq", "USDC", "asset check"),
            ConditionalSignRule("args.operation", "in", ["SUPPLY", "WITHDRAW"], "op check"),
        ]
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=rules)
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_index_reported_in_violation(self) -> None:
        """複数ルールのうち 2 番目が失敗した場合、インデックス [1] が報告されること。"""
        rules = [
            ConditionalSignRule("args.asset", "eq", "USDC", "valid"),
            ConditionalSignRule("", "eq", "foo", "desc"),  # field_path 空
        ]
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=rules)
        _assert_violation_contains(spec, "conditional_signs[1]")


# ---------------------------------------------------------------------------
# WalletPolicySpec 全体バリデーション
# ---------------------------------------------------------------------------


class TestWalletPolicySpec:
    def test_valid_full_spec_passes(self) -> None:
        spec = _valid_spec()
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_invalid_wallet_address_fails(self) -> None:
        spec = _valid_spec(wallet_address="0xBAD")
        _assert_violation_contains(spec, "valid Ethereum address")

    def test_wallet_address_without_0x_fails(self) -> None:
        spec = _valid_spec(wallet_address="abcdef1234567890abcdef1234567890abcdef12")
        _assert_violation_contains(spec, "valid Ethereum address")

    def test_empty_policy_id_fails(self) -> None:
        spec = _valid_spec(policy_id="")
        _assert_violation_contains(spec, "policy_id must not be empty")

    def test_whitespace_policy_id_fails(self) -> None:
        spec = _valid_spec(policy_id="   ")
        _assert_violation_contains(spec, "policy_id must not be empty")

    def test_no_rules_at_all_fails(self) -> None:
        spec = _valid_spec(allowlist=None, spending_limit=None, conditional_signs=[])
        _assert_violation_contains(spec, "at least one rule")

    def test_only_allowlist_sufficient(self) -> None:
        spec = _valid_spec(spending_limit=None, conditional_signs=[])
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_only_spending_limit_sufficient(self) -> None:
        spec = _valid_spec(allowlist=None, conditional_signs=[])
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_only_conditional_signs_sufficient(self) -> None:
        spec = _valid_spec(
            allowlist=None,
            spending_limit=None,
            conditional_signs=[_valid_conditional_sign()],
        )
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_multiple_violations_reported(self) -> None:
        """複数の違反がある場合、全て報告されること。"""
        spec = WalletPolicySpec(
            wallet_address="0xBAD",
            policy_id="",
            allowlist=None,
            spending_limit=None,
            conditional_signs=[],
        )
        with pytest.raises(WalletPolicyValidationError) as exc_info:
            validate_wallet_policy_spec(spec)
        assert len(exc_info.value.violations) >= 3  # address + policy_id + no rules

    def test_wallet_policy_validation_error_message(self) -> None:
        """WalletPolicyValidationError.violations が violations リストを持つ。"""
        spec = _valid_spec(wallet_address="0xBAD", policy_id="")
        with pytest.raises(WalletPolicyValidationError) as exc_info:
            validate_wallet_policy_spec(spec)
        assert isinstance(exc_info.value.violations, list)
        assert len(exc_info.value.violations) >= 1

    def test_valid_wallet_address_checksum_uppercase_accepted(self) -> None:
        """大文字 hex も有効な Ethereum アドレス形式として受け付ける。"""
        spec = _valid_spec(wallet_address="0xABCDEF1234567890ABCDEF1234567890ABCDEF12")
        validate_wallet_policy_spec(spec)  # 例外なし

    def test_frozen_dataclass_immutable(self) -> None:
        """frozen=True により変更不可であることを確認。"""
        spec = _valid_spec()
        with pytest.raises((AttributeError, TypeError)):
            spec.policy_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 安全境界テスト: Privy/tx/秘密鍵が混入していないこと
# ---------------------------------------------------------------------------


class TestSafetyBoundary:
    """
    wallet_policy.py が Privy API 呼出・tx 送信・秘密鍵に依存しないことの
    ランタイム確認。モジュールのインポートと純粋関数実行のみ検証。
    """

    def test_module_imports_no_requests(self) -> None:
        """requests / httpx が wallet_policy に混入していないことを確認。"""
        import app.policy.wallet_policy as wpm

        # wallet_policy モジュール自体の __dict__ に requests/httpx がないこと
        module_dict = vars(wpm)
        assert "requests" not in module_dict
        assert "httpx" not in module_dict

    def test_no_transaction_or_key_attributes(self) -> None:
        """WalletPolicySpec に秘密鍵・tx 送信に関する属性がないこと。"""
        import app.policy.wallet_policy as wpm

        forbidden = ["private_key", "send_raw", "sign_transaction", "privy_api"]
        module_attrs = dir(wpm)
        for attr in forbidden:
            assert attr not in module_attrs, f"Forbidden attribute '{attr}' found in wallet_policy"

    def test_pure_function_no_side_effects(self) -> None:
        """バリデーション関数が外部副作用なしで動作すること。"""
        spec = _valid_spec()
        # 複数回実行しても同じ結果 (純粋関数)
        validate_wallet_policy_spec(spec)
        validate_wallet_policy_spec(spec)
        # 例外なしで完了すれば OK
