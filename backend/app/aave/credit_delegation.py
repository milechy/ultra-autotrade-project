# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/credit_delegation.py
"""Credit Delegation の安全枠計算（純関数）。

Aave V3 Credit Delegation でユーザーが borrowing power を UATa 運用アドレスへ委譲する際の、
**委譲枠上限と HF 影響の計算のみ**を提供する純関数群（Asana 1215620587799245 の第1スライス）。
on-chain の approveDelegation / borrow_on_behalf・web3・秘密鍵・frontend は含まない
（後続 HUMAN-REVIEW スライス）。

Aave protocol は委譲額の法的上限を enforce しないため、**UATa 側で委譲枠上限ロジックを持つ**
（タスク注意点）。本 module はその上限計算 = 「HF floor(1.6) を割らずに委譲先が借りられる最大額」+
任意の絶対委譲上限の二重クランプを担う。

借入後の Health Factor::

    HF = collateral * liquidation_threshold / (existing_debt + borrow)

を HF floor 以上に保つ最大 borrow を解く。金融計算は Decimal のみ（Rule 11）。副作用なし・dormant。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# CLAUDE.md §Security Rule 2: HF < 1.6 → HARD_STOP。委譲借入もこの floor を割ってはならない。
DEFAULT_HF_FLOOR = Decimal("1.6")


class CreditDelegationError(ValueError):
    """入力が委譲枠計算の前提を満たさない。"""


@dataclass(frozen=True)
class DelegationAssessment:
    """委譲借入の安全枠評価（実行はしない）。"""

    requested_usd: Decimal
    """要求された委譲借入額（USD）。"""

    approved_usd: Decimal
    """承認可能な借入額（USD）= min(要求, HF floor 上限, 絶対委譲上限)。"""

    max_borrow_usd: Decimal
    """HF floor を割らない最大借入額（USD）。"""

    projected_hf: Optional[Decimal]
    """approved_usd 借入後の HF。借入後 debt=0 は None。"""

    within_floor: bool
    """approved_usd 借入後も HF が floor 以上か。"""

    reason: str
    """判定理由（監査・ログ用）。"""


def compute_max_delegated_borrow(
    *,
    collateral_usd: Decimal,
    existing_debt_usd: Decimal,
    liquidation_threshold: Decimal,
    hf_floor: Decimal = DEFAULT_HF_FLOOR,
) -> Decimal:
    """HF floor を割らずに追加で借りられる最大額（USD）。負にはならない（0 で下限）。

    HF = collateral*lt/(debt+B) >= floor  ⇔  B <= collateral*lt/floor - debt。
    """
    if collateral_usd < 0 or existing_debt_usd < 0:
        raise CreditDelegationError("collateral_usd / existing_debt_usd must be non-negative")
    if liquidation_threshold <= 0 or liquidation_threshold > 1:
        raise CreditDelegationError("liquidation_threshold must be in (0, 1]")
    if hf_floor <= 0:
        raise CreditDelegationError("hf_floor must be positive")

    headroom = (collateral_usd * liquidation_threshold) / hf_floor - existing_debt_usd
    return headroom if headroom > 0 else Decimal("0")


def assess_delegated_borrow(
    *,
    collateral_usd: Decimal,
    existing_debt_usd: Decimal,
    requested_borrow_usd: Decimal,
    liquidation_threshold: Decimal,
    hf_floor: Decimal = DEFAULT_HF_FLOOR,
    delegation_cap_usd: Optional[Decimal] = None,
) -> DelegationAssessment:
    """委譲借入の安全枠を評価する（計算のみ・実行しない）。

    approved = min(requested, HF floor 上限, 絶対委譲上限) の二重クランプ。

    :param delegation_cap_usd: UATa 側の絶対委譲上限（任意）。None なら HF floor 上限のみ。
    :raises CreditDelegationError: 入力不正
    """
    if requested_borrow_usd < 0:
        raise CreditDelegationError("requested_borrow_usd must be non-negative")
    if delegation_cap_usd is not None and delegation_cap_usd < 0:
        raise CreditDelegationError("delegation_cap_usd must be non-negative")

    max_borrow = compute_max_delegated_borrow(
        collateral_usd=collateral_usd,
        existing_debt_usd=existing_debt_usd,
        liquidation_threshold=liquidation_threshold,
        hf_floor=hf_floor,
    )

    approved = min(requested_borrow_usd, max_borrow)
    capped_by_delegation = False
    if delegation_cap_usd is not None and approved > delegation_cap_usd:
        approved = delegation_cap_usd
        capped_by_delegation = True

    total_debt = existing_debt_usd + approved
    if total_debt <= 0:
        projected_hf: Optional[Decimal] = None
        within_floor = True
    else:
        projected_hf = (collateral_usd * liquidation_threshold) / total_debt
        within_floor = projected_hf >= hf_floor

    if approved <= 0:
        reason = "no borrow headroom — HF floor already binding"
    elif capped_by_delegation:
        reason = "approved amount clamped by delegation cap"
    elif approved < requested_borrow_usd:
        reason = "approved amount clamped by HF floor"
    else:
        reason = "requested amount fully approved within HF floor"

    return DelegationAssessment(
        requested_usd=requested_borrow_usd,
        approved_usd=approved,
        max_borrow_usd=max_borrow,
        projected_hf=projected_hf,
        within_floor=within_floor,
        reason=reason,
    )
