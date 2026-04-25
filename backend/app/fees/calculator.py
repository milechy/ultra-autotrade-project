# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/calculator.py
"""Fee Model v10 月次手数料計算エンジン (F-5)。

v10 spec §3 / §7 の 5 収益ロジックを **純粋関数** として実装する。
I/O / 外部 API / DB 接続は一切行わない。

5 収益ロジック:
    Step 1: net_profit = gross_profit - expense
    Step 2: subscription = deposit * subscription_rate (初月無料)
    Step 3: サブスク保護 (net_profit < subscription なら全額 UATa, fee 0, takehome 0)
    Step 4: tier-based fee = max(0, net_profit - subscription) * fee_rate
    Step 5: monthly_yield_cap (provisional_takehome > cap_amount なら excess→UATa)
    Step 6: affiliate = subscription * affiliate_rate (subscription>0 のみ)

関連:
- 入力源 ``FeeConfigV10`` (F-1 + F-4 seed)
- ``RISK_MODE_SUBSCRIPTION_RATES`` (F-3 内部値直参照、本モジュールでは config 経由で取得)
- ``InvestmentTier`` / ``RiskMode`` (F-2 / F-3)
- ``FeeTransaction`` 出力先 (F-7 月次バッチ)
- ``docs/45_fee_model_v10_migration_plan.md`` §4 F-5 行
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Final

from app.auth.models import InvestmentTier, RiskMode
from app.billing.v10_models import FeeConfigV10

#: 円未満切り捨て (ROUND_DOWN, 整数 JPY 用 Decimal 量子化単位)。
#: ``Decimal("1234.56").quantize(JPY_QUANTIZE, rounding=ROUND_DOWN) == Decimal("1234")``
JPY_QUANTIZE: Final[Decimal] = Decimal("1")

#: tier → tier_fee_rates / tier_monthly_yield_caps 配列の index。
#: GENERAL は LOWER 扱い (F-2 LEGACY_TIER_MAP と同方針)。
_TIER_INDEX: Final[dict[InvestmentTier, int]] = {
    InvestmentTier.LOWER: 0,
    InvestmentTier.MIDDLE: 1,
    InvestmentTier.UPPER: 2,
    InvestmentTier.GENERAL: 0,  # DEPRECATED, F-13 で削除
}


@dataclass(frozen=True)
class FeeCalculationInput:
    """月次手数料計算の入力。

    全ての金額は ``Decimal`` (JPY 単位)。``user_tier`` / ``user_risk_mode``
    は enum で渡し、内部値文字列への変換は本モジュールが行う。
    """

    user_id: int
    calculation_month: date
    deposit_jpy: Decimal
    gross_profit_jpy: Decimal
    expense_jpy: Decimal
    user_tier: InvestmentTier
    user_risk_mode: RiskMode
    affiliate_id: int | None = None
    is_first_month: bool = False


@dataclass(frozen=True)
class FeeCalculationResult:
    """月次手数料計算の出力。``FeeTransaction`` レコードに直接マッピング可能。

    ``tier`` / ``risk_mode`` は CHECK 制約 (F-1 + F-4 046) に準拠した文字列。
    """

    user_id: int
    calculation_month: date
    tier: str
    risk_mode: str
    deposit_jpy: Decimal
    gross_profit_jpy: Decimal
    expense_jpy: Decimal
    net_profit_jpy: Decimal
    fee_rate_applied: Decimal
    fee_amount_jpy: Decimal
    subscription_rate_applied: Decimal
    subscription_amount_jpy: Decimal
    subscription_protected: bool
    monthly_yield_cap_applied: Decimal
    yield_excess_to_uata_jpy: Decimal
    user_takehome_jpy: Decimal
    affiliate_id: int | None
    affiliate_amount_jpy: Decimal
    debug_log: list[str] = field(default_factory=list)


def _normalize_tier_for_db(tier: InvestmentTier) -> str:
    """``InvestmentTier`` → ``fee_transactions.tier`` CHECK 制約準拠の文字列。

    GENERAL (F-2 deprecated) は LOWER に正規化する。
    """
    if tier == InvestmentTier.GENERAL:
        return str(InvestmentTier.LOWER.value)
    return str(tier.value)


class FeeCalculator:
    """v10 5 収益ロジックの純粋関数エンジン。

    インスタンス化時に ``FeeConfigV10`` を受け取り、以後 ``calculate_monthly``
    呼び出しは self.config 以外の外部依存を持たない。
    """

    def __init__(self, fee_config: FeeConfigV10) -> None:
        self.config = fee_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_monthly(self, payload: FeeCalculationInput) -> FeeCalculationResult:
        """月次手数料を計算する (純粋関数)。

        Args:
            payload: 月次集計済みのユーザー単位入力。

        Returns:
            ``FeeTransaction`` レコードに直接マッピング可能な計算結果。
        """
        debug: list[str] = []

        # === Step 1: net_profit ===
        net_profit = self._round_jpy(payload.gross_profit_jpy - payload.expense_jpy)
        debug.append(
            f"step1 net_profit = {payload.gross_profit_jpy} - {payload.expense_jpy} = {net_profit}"
        )

        # === Step 2: subscription ===
        sub_rate = self._get_subscription_rate(payload.user_risk_mode, payload.is_first_month)
        sub_amount = self._round_jpy(payload.deposit_jpy * sub_rate)
        debug.append(
            f"step2 subscription: deposit({payload.deposit_jpy}) * rate({sub_rate}) = {sub_amount}"
        )

        # === Step 3: サブスク保護 ===
        # net_profit < sub_amount かつ sub_amount > 0 のとき発動。
        # 利益全額を UATa に回し、fee も affiliate もゼロにする。
        if sub_amount > Decimal("0") and net_profit < sub_amount:
            debug.append(
                f"step3 SUBSCRIPTION_PROTECTED: net({net_profit}) < sub({sub_amount}) "
                "→ all profit to UATa"
            )
            return FeeCalculationResult(
                user_id=payload.user_id,
                calculation_month=payload.calculation_month,
                tier=_normalize_tier_for_db(payload.user_tier),
                risk_mode=payload.user_risk_mode.value,
                deposit_jpy=payload.deposit_jpy,
                gross_profit_jpy=payload.gross_profit_jpy,
                expense_jpy=payload.expense_jpy,
                net_profit_jpy=net_profit,
                fee_rate_applied=Decimal("0"),
                fee_amount_jpy=Decimal("0"),
                subscription_rate_applied=sub_rate,
                subscription_amount_jpy=Decimal("0"),
                subscription_protected=True,
                monthly_yield_cap_applied=Decimal("0"),
                yield_excess_to_uata_jpy=net_profit,
                user_takehome_jpy=Decimal("0"),
                affiliate_id=None,
                affiliate_amount_jpy=Decimal("0"),
                debug_log=debug,
            )

        # === Step 4: tier-based fee ===
        fee_rate = self._get_tier_fee_rate(payload.user_tier)
        fee_base = net_profit - sub_amount
        if fee_base > Decimal("0"):
            fee_amount = self._round_jpy(fee_base * fee_rate)
        else:
            fee_amount = Decimal("0")
        debug.append(f"step4 fee: ({net_profit} - {sub_amount}) * {fee_rate} = {fee_amount}")

        # === Step 5: monthly_yield_cap ===
        cap_rate = self._get_monthly_yield_cap(payload.user_tier)
        cap_amount = self._round_jpy(payload.deposit_jpy * cap_rate)
        provisional_takehome = net_profit - sub_amount - fee_amount

        if provisional_takehome > cap_amount:
            yield_excess = provisional_takehome - cap_amount
            user_takehome = cap_amount
            debug.append(
                f"step5 YIELD_CAP: provisional({provisional_takehome}) > cap({cap_amount}) "
                f"→ excess({yield_excess}) to UATa"
            )
        else:
            yield_excess = Decimal("0")
            user_takehome = provisional_takehome
            debug.append(
                f"step5 yield ok: provisional({provisional_takehome}) <= cap({cap_amount})"
            )

        # === Step 6: affiliate ===
        if payload.affiliate_id is not None and sub_amount > Decimal("0"):
            affiliate_amount = self._round_jpy(sub_amount * self._affiliate_rate())
            affiliate_id_out: int | None = payload.affiliate_id
            debug.append(
                f"step6 affiliate: sub({sub_amount}) * rate({self._affiliate_rate()}) "
                f"= {affiliate_amount}"
            )
        else:
            affiliate_amount = Decimal("0")
            affiliate_id_out = None
            debug.append(f"step6 affiliate skipped: id={payload.affiliate_id}, sub={sub_amount}")

        return FeeCalculationResult(
            user_id=payload.user_id,
            calculation_month=payload.calculation_month,
            tier=_normalize_tier_for_db(payload.user_tier),
            risk_mode=payload.user_risk_mode.value,
            deposit_jpy=payload.deposit_jpy,
            gross_profit_jpy=payload.gross_profit_jpy,
            expense_jpy=payload.expense_jpy,
            net_profit_jpy=net_profit,
            fee_rate_applied=fee_rate,
            fee_amount_jpy=fee_amount,
            subscription_rate_applied=sub_rate,
            subscription_amount_jpy=sub_amount,
            subscription_protected=False,
            monthly_yield_cap_applied=cap_rate,
            yield_excess_to_uata_jpy=yield_excess,
            user_takehome_jpy=user_takehome,
            affiliate_id=affiliate_id_out,
            affiliate_amount_jpy=affiliate_amount,
            debug_log=debug,
        )

    # ------------------------------------------------------------------
    # Internal helpers (純粋関数)
    # ------------------------------------------------------------------

    @staticmethod
    def _round_jpy(value: Decimal) -> Decimal:
        """円未満切り捨て (ROUND_DOWN, 0 方向に丸める)。

        正の値: 1234.56 → 1234
        負の値: -1234.56 → -1234 (ROUND_DOWN は 0 に向かって切り捨て)
        """
        return value.quantize(JPY_QUANTIZE, rounding=ROUND_DOWN)

    def _get_subscription_rate(self, risk_mode: RiskMode, is_first_month: bool) -> Decimal:
        """``FeeConfigV10.subscription_rates`` JSONB から取得。初月は 0。"""
        if is_first_month:
            return Decimal("0")
        rates = self.config.subscription_rates
        return Decimal(str(rates.get(risk_mode.value, 0)))

    def _get_tier_fee_rate(self, tier: InvestmentTier) -> Decimal:
        """``FeeConfigV10.tier_fee_rates`` から tier index で取得。"""
        rates = self.config.tier_fee_rates
        return Decimal(str(rates[_TIER_INDEX[tier]]))

    def _get_monthly_yield_cap(self, tier: InvestmentTier) -> Decimal:
        """``FeeConfigV10.tier_monthly_yield_caps`` から tier index で取得。"""
        caps = self.config.tier_monthly_yield_caps
        return Decimal(str(caps[_TIER_INDEX[tier]]))

    def _affiliate_rate(self) -> Decimal:
        """``FeeConfigV10.affiliate_rate`` (Numeric → Decimal)。"""
        return Decimal(str(self.config.affiliate_rate))
