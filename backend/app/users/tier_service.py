# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/tier_service.py
"""
投資ティア判定サービス。

v10 三層戦略 (F-2 2026-04-25 〜):
  LOWER:  deposit_jpy <= 1,000,000
  MIDDLE: 1,000,001 <= deposit_jpy <= 10,000,000
  UPPER:  deposit_jpy >= 10,000,001

v9 二層戦略 (パートナー配下の active 割り振り合計 USD):
  GENERAL: total_allocated_usd < TIER_THRESHOLD_USD (≒ $20,000)
  UPPER:   total_allocated_usd >= TIER_THRESHOLD_USD

  v9 経路 (refresh_partner_tier) は本タスクでも残置するが、戻り値は v10 LOWER/UPPER
  に揃えた (GENERAL は廃止予定の互換値)。F-13 で完全廃止予定。
"""

import logging
import os
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.models import (
    TIER_BOUNDARY_LOWER_JPY,
    TIER_BOUNDARY_UPPER_JPY,
    InvestmentTier,
    User,
)
from app.partner.allocation_models import FundAllocation

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_USD = Decimal("20000")


def _get_threshold() -> Decimal:
    raw = os.getenv("TIER_THRESHOLD_USD", "")
    if raw:
        try:
            return Decimal(raw)
        except Exception:
            logger.warning("[tier_service] Invalid TIER_THRESHOLD_USD=%r; using default", raw)
    return _DEFAULT_THRESHOLD_USD


def determine_tier(total_allocated_usd: Decimal) -> str:
    """
    v9 互換: 割り振り合計額 (USD) からティアを判定する。

    F-2 までは ``"GENERAL" / "UPPER"`` を返していたが、v10 移行に伴い
    GENERAL → ``InvestmentTier.LOWER.value`` に置換した。F-16 マイグレーションで
    既存 6 ユーザーの ``users.tier`` GENERAL レコードが LOWER/MIDDLE/UPPER に
    再判定される。

    Args:
        total_allocated_usd: パートナー配下の active 割り振り合計額（USD, Decimal）

    Returns:
        "LOWER" または "UPPER"
    """
    threshold = _get_threshold()
    if total_allocated_usd >= threshold:
        return InvestmentTier.UPPER.value
    return InvestmentTier.LOWER.value


def determine_tier_jpy(deposit_jpy: Decimal) -> InvestmentTier:
    """
    v10: ユーザーのデポジット額 (JPY) からティアを判定する。

    境界:
      LOWER:  deposit_jpy <= 1,000,000
      MIDDLE: 1,000,001 <= deposit_jpy <= 10,000,000
      UPPER:  deposit_jpy >= 10,000,001

    Args:
        deposit_jpy: ユーザーのデポジット額（JPY, Decimal）

    Returns:
        InvestmentTier (LOWER / MIDDLE / UPPER)
    """
    if deposit_jpy <= Decimal(TIER_BOUNDARY_LOWER_JPY):
        return InvestmentTier.LOWER
    if deposit_jpy <= Decimal(TIER_BOUNDARY_UPPER_JPY):
        return InvestmentTier.MIDDLE
    return InvestmentTier.UPPER


def refresh_partner_tier(db: Session, partner_id: int) -> str:
    """
    パートナーの active 割り振り合計を集計して tier を再計算・DB 更新する。

    Returns:
        新しい tier 値
    """
    total_raw = (
        db.query(func.sum(FundAllocation.allocated_amount_usd))
        .filter(
            FundAllocation.partner_id == partner_id,
            FundAllocation.status == "active",
        )
        .scalar()
    )
    total = Decimal(str(total_raw)) if total_raw else Decimal("0")
    new_tier = determine_tier(total)

    db.query(User).filter(User.id == partner_id).update({"tier": new_tier})
    db.commit()
    logger.info("[tier_service] partner_id=%d total_usd=%s tier=%s", partner_id, total, new_tier)
    return new_tier
