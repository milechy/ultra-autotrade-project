# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/self_liquidation.py
"""自己清算保護（Flash Loan デレバレッジ）の純計算層。

HF が危険域に近づいたとき、外部清算業者に清算されてペナルティ（5-10%）を払う前に、
Flash Loan で自力デレバレッジ（debt の一部を返済して HF を回復）する戦略の**計算のみ**を
提供する純関数群。Solidity コントラクト・on-chain 実行・web3・秘密鍵は一切含まない
（Asana 1215620828227794 の第1スライス）。

デレバレッジの原子的フロー（実行は後続 HUMAN-REVIEW スライス）::

    1. USDC を Flash Loan で借りる（amount = 返済する debt 額）
    2. その USDC で Aave の debt を `amount` だけ返済
    3. 担保を `amount * (1 + fee)` 相当だけ引き出す
    4. Flash Loan を `amount * (1 + fee)` で返済（手数料込み）

返済後の Health Factor::

    HF = (collateral - amount*(1+fee)) * liquidation_threshold / (debt - amount)

を目標 HF に一致させる返済額 `amount` を解析的に解く。金融計算は Decimal のみ（Rule 11）。

**dormant**: 本 module は計算だけで副作用なし。実行（flash_loan_service / SelfLiquidator.sol）・
workflow 統合・frontend は別スライス（Tier S / HUMAN-REVIEW）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Aave V3 の Flash Loan 手数料（flashLoanSimple は 0.05%）。
DEFAULT_FLASH_LOAN_FEE_RATE = Decimal("0.0005")

# 既定の発動トリガー（current_hf がこの値未満で自己清算保護を検討）。HARD_STOP(1.6) より手前。
DEFAULT_TRIGGER_HF = Decimal("1.3")

# デレバレッジ後に回復させる目標 HF（HARD_STOP 1.6 に十分なマージンを足す）。
DEFAULT_TARGET_HF = Decimal("1.8")


class SelfLiquidationError(ValueError):
    """入力が自己清算計算の前提を満たさない。"""


@dataclass(frozen=True)
class DeleverageQuote:
    """自己清算デレバレッジの見積り（実行はしない）。"""

    feasible: bool
    """この入力で目標 HF まで回復可能か。"""

    repay_debt_usd: Decimal
    """返済する debt 額（USD）= Flash Loan で借りる USDC 額。"""

    flash_loan_fee_usd: Decimal
    """Flash Loan 手数料（USD）= repay_debt_usd * fee_rate。"""

    collateral_withdraw_usd: Decimal
    """引き出す担保額（USD）= repay_debt_usd + 手数料（Flash Loan 返済に充てる）。"""

    projected_hf: Optional[Decimal]
    """デレバレッジ後の HF。全 debt 返済（debt=0）になる場合は None（実質無限大）。"""

    reason: str
    """判定理由（監査・ログ用）。"""


def compute_health_factor(
    collateral_usd: Decimal, debt_usd: Decimal, liquidation_threshold: Decimal
) -> Optional[Decimal]:
    """HF = collateral * liquidation_threshold / debt。debt=0 は None（無限大）。"""
    if debt_usd <= 0:
        return None
    return (collateral_usd * liquidation_threshold) / debt_usd


def should_protect(current_hf: Optional[Decimal], trigger_hf: Decimal = DEFAULT_TRIGGER_HF) -> bool:
    """自己清算保護を発動検討すべきか（current_hf が trigger 未満）。

    debt 無し（current_hf=None）は対象外（清算リスクなし）。
    """
    if current_hf is None:
        return False
    return current_hf < trigger_hf


def compute_deleverage_quote(
    *,
    collateral_usd: Decimal,
    debt_usd: Decimal,
    liquidation_threshold: Decimal,
    target_hf: Decimal = DEFAULT_TARGET_HF,
    flash_loan_fee_rate: Decimal = DEFAULT_FLASH_LOAN_FEE_RATE,
) -> DeleverageQuote:
    """目標 HF まで回復するデレバレッジ見積りを返す（計算のみ・実行しない）。

    :raises SelfLiquidationError: 入力が不正（負値 / liquidation_threshold が範囲外 / target<=0）
    """
    if collateral_usd < 0 or debt_usd < 0:
        raise SelfLiquidationError("collateral_usd / debt_usd must be non-negative")
    if liquidation_threshold <= 0 or liquidation_threshold > 1:
        raise SelfLiquidationError("liquidation_threshold must be in (0, 1]")
    if target_hf <= 0:
        raise SelfLiquidationError("target_hf must be positive")
    if flash_loan_fee_rate < 0:
        raise SelfLiquidationError("flash_loan_fee_rate must be non-negative")

    zero = Decimal("0")

    # debt が無ければ清算リスクなし＝デレバレッジ不要。
    if debt_usd <= 0:
        return DeleverageQuote(
            feasible=False,
            repay_debt_usd=zero,
            flash_loan_fee_usd=zero,
            collateral_withdraw_usd=zero,
            projected_hf=None,
            reason="no debt — deleverage not needed",
        )

    current_hf = (collateral_usd * liquidation_threshold) / debt_usd
    if current_hf >= target_hf:
        return DeleverageQuote(
            feasible=False,
            repay_debt_usd=zero,
            flash_loan_fee_usd=zero,
            collateral_withdraw_usd=zero,
            projected_hf=current_hf,
            reason="HF already at or above target — no action needed",
        )

    one_plus_fee = Decimal("1") + flash_loan_fee_rate
    # amount = (target*debt - collateral*lt) / (target - (1+fee)*lt)
    numerator = target_hf * debt_usd - collateral_usd * liquidation_threshold
    denominator = target_hf - one_plus_fee * liquidation_threshold
    if denominator <= 0:
        # target_hf <= (1+fee)*lt の病的ケース（担保引き出しで HF が上がらない）。
        return DeleverageQuote(
            feasible=False,
            repay_debt_usd=zero,
            flash_loan_fee_usd=zero,
            collateral_withdraw_usd=zero,
            projected_hf=current_hf,
            reason="target_hf is not reachable for this liquidation_threshold/fee",
        )

    amount = numerator / denominator
    if amount <= 0:
        return DeleverageQuote(
            feasible=False,
            repay_debt_usd=zero,
            flash_loan_fee_usd=zero,
            collateral_withdraw_usd=zero,
            projected_hf=current_hf,
            reason="no positive repayment restores target HF",
        )

    # debt 全額を超える返済は不要（全返済で HF は無限大）。
    full_repayment = amount >= debt_usd
    repay = debt_usd if full_repayment else amount
    fee = repay * flash_loan_fee_rate
    withdraw = repay + fee

    # 引き出す担保が現在の担保を超えるなら自己清算では回復不能（fail-closed）。
    if withdraw > collateral_usd:
        return DeleverageQuote(
            feasible=False,
            repay_debt_usd=zero,
            flash_loan_fee_usd=zero,
            collateral_withdraw_usd=zero,
            projected_hf=current_hf,
            reason="insufficient collateral to withdraw for repayment + fee",
        )

    remaining_debt = debt_usd - repay
    if remaining_debt <= 0:
        projected = None
    else:
        projected = ((collateral_usd - withdraw) * liquidation_threshold) / remaining_debt

    return DeleverageQuote(
        feasible=True,
        repay_debt_usd=repay,
        flash_loan_fee_usd=fee,
        collateral_withdraw_usd=withdraw,
        projected_hf=projected,
        reason="full debt repayment restores safety"
        if full_repayment
        else "partial deleverage restores target HF",
    )
