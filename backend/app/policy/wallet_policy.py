# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/policy/wallet_policy.py
"""
Privy server-side policy の宣言的スキーマとバリデータ。

Phase 1 (scaffold): 純粋なデータクラスとバリデーション関数のみ。
Privy API 呼出・tx 送信・署名・秘密鍵は一切含まない。
既存 PolicyEngine (engine.py) を import/改変しない。

二層ポリシー構造における位置づけ:
  - 本モジュール: application-layer の宣言的スキーマ定義
  - engine.py:    application-layer の hard rule 検算
  - Phase 3 (HUMAN-REVIEW-REQUIRED): Privy API 呼出層 (別モジュール)
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional, Union

# 金融計算規則 (Security Rule 11): 全金融値は Decimal 型のみ。float 禁止。

# ---- 定数 ----

_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_CONDITIONAL_OPERATORS: frozenset[str] = frozenset(
    {"eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in"}
)
_LIST_OPERATORS: frozenset[str] = frozenset({"in", "not_in"})
_SCALAR_OPERATORS: frozenset[str] = _CONDITIONAL_OPERATORS - _LIST_OPERATORS


# ---- バリデーションエラー ----


class WalletPolicyValidationError(ValueError):
    """WalletPolicySpec のバリデーション違反。"""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


# ---- ルール定義 ----


@dataclass(frozen=True)
class WalletAllowlistRule:
    """
    宛先コントラクトアドレス / 資産シンボルの allowlist。
    Privy server policy の allowlist 設定に対応する。

    注意: Privy は動的自己参照 (onBehalfOf == msg.sender) を未サポート。
    calldata 本人一致検証は aave/client.py の _decode_pool_calldata で担保する。
    """

    allowed_contracts: frozenset[str]
    """許可コントラクトアドレス。小文字 0x... 形式で保持される。"""

    allowed_assets: frozenset[str]
    """許可資産シンボル。大文字で保持される (例: "USDC")。"""


@dataclass(frozen=True)
class SpendingLimitRule:
    """
    期間内送金上限。Privy server policy の spending_limit 設定に対応する。
    金融計算規則 (Rule 11): 全フィールドは Decimal 型必須。float 禁止。
    """

    per_transaction_usd: Decimal
    """単一 tx の USD 上限。正値必須。"""

    per_day_usd: Decimal
    """日次 USD 上限。per_transaction_usd 以上必須。"""

    per_week_usd: Optional[Decimal] = None
    """週次 USD 上限 (省略可)。指定時は per_day_usd 以上必須。"""


@dataclass(frozen=True)
class ConditionalSignRule:
    """
    条件付き署名ルール。Privy server policy の conditional_sign 設定に対応する。
    Privy は静的リテラル値のみ比較可能 (動的自己参照は未サポート)。
    """

    field_path: str
    """チェック対象 calldata フィールドパス (空不可)。"""

    operator: Literal["eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in"]
    """比較演算子。"""

    value: Union[str, list[str]]
    """
    比較値 (静的リテラルのみ)。
    in / not_in 演算子のとき list[str]、それ以外のとき str。
    """

    description: str
    """ルール説明 (監査ログ用)。空不可。"""


@dataclass(frozen=True)
class WalletPolicySpec:
    """
    Privy server-side policy の完全仕様。
    `validate_wallet_policy_spec()` でバリデーションしてから使用する。
    """

    wallet_address: str
    """対象ウォレットアドレス (0x prefix + 40 hex 文字)。"""

    policy_id: str
    """識別子 (監査ログ用、空不可)。"""

    allowlist: Optional[WalletAllowlistRule] = None
    """allowlist ルール (省略可)。"""

    spending_limit: Optional[SpendingLimitRule] = None
    """spending limit ルール (省略可)。"""

    conditional_signs: list[ConditionalSignRule] = field(default_factory=list)
    """条件付き署名ルール (0 個以上)。"""


# ---- ファクトリ関数 ----


def make_allowlist_rule(
    allowed_contracts: list[str],
    allowed_assets: list[str],
) -> WalletAllowlistRule:
    """
    WalletAllowlistRule を構築し、正規化する。
    - コントラクトアドレスは小文字に正規化
    - 資産シンボルは大文字に正規化
    バリデーションは `validate_wallet_policy_spec()` で行う。
    """
    return WalletAllowlistRule(
        allowed_contracts=frozenset(addr.lower() for addr in allowed_contracts),
        allowed_assets=frozenset(asset.upper() for asset in allowed_assets),
    )


def make_spending_limit_rule(
    per_transaction_usd: Union[str, Decimal],
    per_day_usd: Union[str, Decimal],
    per_week_usd: Optional[Union[str, Decimal]] = None,
) -> SpendingLimitRule:
    """
    SpendingLimitRule を構築する。
    文字列も受け付けるが内部では Decimal 型に変換する (Rule 11 準拠)。
    バリデーションは `validate_wallet_policy_spec()` で行う。
    """
    return SpendingLimitRule(
        per_transaction_usd=_coerce_decimal(per_transaction_usd, "per_transaction_usd"),
        per_day_usd=_coerce_decimal(per_day_usd, "per_day_usd"),
        per_week_usd=_coerce_decimal(per_week_usd, "per_week_usd")
        if per_week_usd is not None
        else None,
    )


# ---- バリデータ ----


def validate_wallet_policy_spec(spec: WalletPolicySpec) -> None:
    """
    WalletPolicySpec の整合性・値域・型を検証する。
    違反がある場合は WalletPolicyValidationError を送出する。
    """
    violations: list[str] = []

    _validate_wallet_address(spec.wallet_address, violations)
    _validate_policy_id(spec.policy_id, violations)

    has_rules = (
        spec.allowlist is not None
        or spec.spending_limit is not None
        or bool(spec.conditional_signs)
    )
    if not has_rules:
        violations.append(
            "WalletPolicySpec must contain at least one rule "
            "(allowlist, spending_limit, or conditional_signs)"
        )

    if spec.allowlist is not None:
        _validate_allowlist_rule(spec.allowlist, violations)

    if spec.spending_limit is not None:
        _validate_spending_limit_rule(spec.spending_limit, violations)

    for i, csr in enumerate(spec.conditional_signs):
        _validate_conditional_sign_rule(csr, i, violations)

    if violations:
        raise WalletPolicyValidationError(violations)


# ---- プライベートバリデーション関数 ----


def _validate_wallet_address(addr: str, violations: list[str]) -> None:
    if not _ETH_ADDRESS_RE.match(addr):
        violations.append(
            f"wallet_address '{addr}' is not a valid Ethereum address (expected 0x + 40 hex chars)"
        )


def _validate_policy_id(policy_id: str, violations: list[str]) -> None:
    if not policy_id.strip():
        violations.append("policy_id must not be empty")


def _validate_allowlist_rule(rule: WalletAllowlistRule, violations: list[str]) -> None:
    if not rule.allowed_contracts:
        violations.append(
            "allowlist.allowed_contracts must not be empty "
            "(empty allowlist implies allow-all, which is unsafe)"
        )
    else:
        for addr in rule.allowed_contracts:
            if not _ETH_ADDRESS_RE.match(addr):
                violations.append(
                    f"allowlist.allowed_contracts contains invalid address '{addr}' "
                    "(expected lowercase 0x + 40 hex chars)"
                )

    if not rule.allowed_assets:
        violations.append("allowlist.allowed_assets must not be empty")


def _validate_spending_limit_rule(rule: SpendingLimitRule, violations: list[str]) -> None:
    # 型チェック (Rule 11: Decimal 型強制)
    for field_name, value in [
        ("per_transaction_usd", rule.per_transaction_usd),
        ("per_day_usd", rule.per_day_usd),
    ]:
        if not isinstance(value, Decimal):
            violations.append(
                f"spending_limit.{field_name} must be Decimal type (got {type(value).__name__})"
            )
        elif value <= Decimal("0"):
            violations.append(f"spending_limit.{field_name} must be positive (got {value})")

    if rule.per_week_usd is not None:
        if not isinstance(rule.per_week_usd, Decimal):
            violations.append(
                f"spending_limit.per_week_usd must be Decimal type "
                f"(got {type(rule.per_week_usd).__name__})"
            )
        elif rule.per_week_usd <= Decimal("0"):
            violations.append(
                f"spending_limit.per_week_usd must be positive (got {rule.per_week_usd})"
            )

    # 矛盾チェック (型エラーがある場合は比較しない)
    tx_ok = isinstance(rule.per_transaction_usd, Decimal) and rule.per_transaction_usd > Decimal(
        "0"
    )
    day_ok = isinstance(rule.per_day_usd, Decimal) and rule.per_day_usd > Decimal("0")
    week_ok = (
        rule.per_week_usd is not None
        and isinstance(rule.per_week_usd, Decimal)
        and rule.per_week_usd > Decimal("0")
    )

    if tx_ok and day_ok and rule.per_transaction_usd > rule.per_day_usd:
        violations.append(
            f"spending_limit: per_transaction_usd ({rule.per_transaction_usd}) "
            f"must not exceed per_day_usd ({rule.per_day_usd})"
        )

    if (
        day_ok
        and week_ok
        and rule.per_week_usd is not None
        and rule.per_day_usd > rule.per_week_usd
    ):
        violations.append(
            f"spending_limit: per_day_usd ({rule.per_day_usd}) "
            f"must not exceed per_week_usd ({rule.per_week_usd})"
        )


def _validate_conditional_sign_rule(
    rule: ConditionalSignRule, index: int, violations: list[str]
) -> None:
    prefix = f"conditional_signs[{index}]"

    if not rule.field_path.strip():
        violations.append(f"{prefix}.field_path must not be empty")

    if rule.operator not in _CONDITIONAL_OPERATORS:
        violations.append(
            f"{prefix}.operator '{rule.operator}' is not valid; "
            f"must be one of {sorted(_CONDITIONAL_OPERATORS)}"
        )

    if not rule.description.strip():
        violations.append(f"{prefix}.description must not be empty")

    if rule.operator in _LIST_OPERATORS:
        if not isinstance(rule.value, list):
            violations.append(
                f"{prefix}.value must be list[str] when operator is '{rule.operator}' "
                f"(got {type(rule.value).__name__})"
            )
        elif not rule.value:
            violations.append(
                f"{prefix}.value list must not be empty when operator is '{rule.operator}'"
            )
    else:
        if isinstance(rule.value, list):
            violations.append(
                f"{prefix}.value must be str when operator is '{rule.operator}' (got list)"
            )


# ---- プライベートヘルパー ----


def _coerce_decimal(value: Union[str, Decimal], field_name: str) -> Decimal:
    """文字列または Decimal を Decimal に変換する。変換失敗時は ValueError を送出。"""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name}: cannot convert '{value}' to Decimal") from exc
