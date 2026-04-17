# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/tier_service.py
"""
投資ティア判定サービス。

二層戦略:
  GENERAL: total_allocated_usd < TIER_THRESHOLD_USD
  UPPER:   total_allocated_usd >= TIER_THRESHOLD_USD

デフォルト閾値: $20,000（≒ 300万円 @ 150円/$）
環境変数 TIER_THRESHOLD_USD で上書き可能。
"""

import logging
import os
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.models import InvestmentTier, User
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
    割り振り合計額からティアを判定する。

    Args:
        total_allocated_usd: パートナー配下の active 割り振り合計額（USD, Decimal）

    Returns:
        "GENERAL" または "UPPER"
    """
    threshold = _get_threshold()
    if total_allocated_usd >= threshold:
        return InvestmentTier.UPPER.value
    return InvestmentTier.GENERAL.value


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
