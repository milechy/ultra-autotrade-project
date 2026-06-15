# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/data_feeds/x402/validators.py
"""
x402 AI自律データ購入 — 純粋バリデータ群 (Phase 0 scaffold)

設計方針:
  - 外部I/O・blockchain・鍵・HTTP に一切触れない pure function のみ
  - 全金額比較は Decimal 演算 (float 禁止 / Security Rules 11)
  - 戻り値は (bool, str | None) — workflow.py の (False, "daily_limit_reached") 形式に準拠
  - 予算超過・不明トークン時は fail-open (購入しない) — data_feeds/context.py 原則と同じ

HUMAN-REVIEW-REQUIRED スコープ (本ファイルでは実装しない):
  - HTTP 402 レスポンス処理
  - facilitator 通信
  - payment header 生成・検証
  - ウォレット署名・秘密鍵操作
"""

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.data_feeds.x402.schemas import X402BudgetPolicy, X402PaymentToken, X402PurchaseIntent


def validate_amount_positive(intent: X402PurchaseIntent) -> None:
    """購入金額が正の値であることを検証する。

    Args:
        intent: 購入意図オブジェクト。

    Raises:
        ValueError: amount_usd が 0 以下または非数値の場合。
    """
    try:
        amount = Decimal(intent.amount_usd)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"amount_usd が Decimal に変換できません: {intent.amount_usd!r}") from exc

    if amount <= Decimal("0"):
        raise ValueError(
            f"amount_usd は正の値である必要があります: {amount} (float 禁止 / Decimal のみ)"
        )


def validate_within_per_request_limit(
    intent: X402PurchaseIntent,
    policy: X402BudgetPolicy,
) -> None:
    """1リクエスト上限以内であることを検証する。

    Args:
        intent: 購入意図オブジェクト。
        policy: 予算ポリシー。

    Raises:
        ValueError: amount_usd が max_per_request_usd を超える場合。
    """
    amount = Decimal(intent.amount_usd)
    limit = Decimal(policy.max_per_request_usd)

    if amount > limit:
        raise ValueError(f"amount_usd ({amount}) が 1リクエスト上限 ({limit}) を超えています")


def validate_within_daily_budget(
    intent: X402PurchaseIntent,
    policy: X402BudgetPolicy,
    spent_today_usd: Decimal,
) -> None:
    """日次予算上限以内であることを検証する。

    workflow.py の daily_limit チェック (daily_traded_usd >= daily_limit) と
    同じ思想: Decimal のみで比較し、超過時は購入不可とする。

    Args:
        intent: 購入意図オブジェクト。
        policy: 予算ポリシー。
        spent_today_usd: 本日の累積購入金額 (Decimal)。float 禁止。

    Raises:
        ValueError: 累積 + 購入予定額が daily_budget_usd を超える場合。
    """
    amount = Decimal(intent.amount_usd)
    spent = Decimal(spent_today_usd)
    budget = Decimal(policy.daily_budget_usd)

    if spent + amount > budget:
        raise ValueError(
            f"日次予算上限超過: 累積 {spent} + 今回 {amount} = {spent + amount}"
            f" が上限 {budget} を超えます (workflow.py daily_limit_reached 相当)"
        )


def validate_token_allowed(
    intent: X402PurchaseIntent,
    allowed_tokens: set[X402PaymentToken],
) -> None:
    """使用トークンが許可集合内であることを検証する。

    Args:
        intent: 購入意図オブジェクト。
        allowed_tokens: 許可されたトークン種別の集合。

    Raises:
        ValueError: intent.token が allowed_tokens に含まれない場合。
    """
    if intent.token not in allowed_tokens:
        raise ValueError(
            f"トークン {intent.token!r} は許可されていません。"
            f"許可リスト: {sorted(t.value for t in allowed_tokens)}"
        )


def validate_purchase_intent(
    intent: X402PurchaseIntent,
    policy: X402BudgetPolicy,
    spent_today_usd: Decimal,
    allowed_tokens: set[X402PaymentToken],
) -> tuple[bool, Optional[str]]:
    """全バリデーションの AND 集約。

    workflow.py の (False, "daily_limit_reached") 形式に揃え、
    呼び出し元が reason を見て fail-open / ログ記録できるようにする。

    Args:
        intent: 購入意図オブジェクト。
        policy: 予算ポリシー。
        spent_today_usd: 本日の累積購入金額 (Decimal)。float 禁止。
        allowed_tokens: 許可トークン集合。

    Returns:
        (True, None): 全バリデーション通過。
        (False, reason): いずれかのバリデーション失敗と理由文字列。
    """
    checks: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = [
        (validate_amount_positive, (intent,), {}),
        (validate_within_per_request_limit, (intent, policy), {}),
        (
            validate_within_daily_budget,
            (intent, policy, spent_today_usd),
            {},
        ),
        (validate_token_allowed, (intent, allowed_tokens), {}),
    ]

    for func, args, kwargs in checks:
        try:
            func(*args, **kwargs)
        except ValueError as exc:
            return False, str(exc)

    return True, None
