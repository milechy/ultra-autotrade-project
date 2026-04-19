# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/risk_limiter.py

"""
Emergency risk limit relaxation for testing (F-17a).

Activated by CUSTOM_LIMITER_ENABLED=true in .env.production.
Auto-reverts to strict mode after CUSTOM_LIMITER_EXPIRES_ON date.

Environment variables:
  CUSTOM_LIMITER_ENABLED=true           Enable custom (relaxed) limits
  CUSTOM_LIMITER_EXPIRES_ON=2026-05-15  Auto-revert date (YYYY-MM-DD)
  CUSTOM_HF_MIN=1.3                     Custom HF minimum
  CUSTOM_SINGLE_TRADE_PCT=20            Single trade max % of total assets
  CUSTOM_DAILY_TRADE_PCT=60             Daily trade max % of total assets
  CUSTOM_COOLDOWN_SECONDS=120           Min seconds between Aave operations

Hard limits (absolute — NEVER overridden regardless of env vars):
  HF minimum:        1.2
  Single trade max:  40%
  Daily trade max:   90%
  Cooldown min:      60s
"""

import logging
import os
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# ---- Hard limits (absolute floor/ceiling — cannot be overridden) ----
HF_HARD_MIN = Decimal("1.2")
SINGLE_TRADE_PCT_HARD_MAX = Decimal("40")
DAILY_TRADE_PCT_HARD_MAX = Decimal("90")
COOLDOWN_HARD_MIN_SECONDS = 60

# ---- Strict defaults (used when custom limiter is disabled or expired) ----
HF_STRICT_DEFAULT = Decimal("1.6")
SINGLE_TRADE_PCT_STRICT_DEFAULT = Decimal("10")
DAILY_TRADE_PCT_STRICT_DEFAULT = Decimal("30")
COOLDOWN_STRICT_DEFAULT_SECONDS = 600


@dataclass(frozen=True)
class EffectiveLimits:
    """Resolved limits after applying custom overrides and hard constraints."""

    hf_min: Decimal
    single_trade_pct_max: Decimal
    daily_trade_pct_max: Decimal
    cooldown_seconds: int
    is_custom: bool
    expires_on: Optional[date]


def _parse_decimal(val: Optional[str], fallback: Decimal) -> Decimal:
    if not val:
        return fallback
    try:
        return Decimal(val.strip())
    except InvalidOperation:
        logger.error("risk_limiter: invalid decimal value %r, using fallback %s", val, fallback)
        return fallback


def _parse_int(val: Optional[str], fallback: int) -> int:
    if not val:
        return fallback
    try:
        return int(val.strip())
    except ValueError:
        logger.error("risk_limiter: invalid int value %r, using fallback %d", val, fallback)
        return fallback


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(val.strip())
    except ValueError:
        logger.error("risk_limiter: invalid date %r for CUSTOM_LIMITER_EXPIRES_ON", val)
        return None


def _is_expired(expires_on: Optional[date]) -> bool:
    """Return True if the custom limiter has passed its expiry date."""
    if expires_on is None:
        return False
    return date.today() > expires_on


def get_effective_limits() -> EffectiveLimits:
    """
    Return the effective risk limits for this process.

    Resolution order:
    1. If CUSTOM_LIMITER_ENABLED != "true" → strict defaults
    2. If today > CUSTOM_LIMITER_EXPIRES_ON → strict defaults (auto-revert)
    3. Otherwise → custom values, clamped to hard limits
    """
    enabled_raw = os.getenv("CUSTOM_LIMITER_ENABLED", "").strip().lower()
    if enabled_raw not in ("true", "1", "yes"):
        return EffectiveLimits(
            hf_min=HF_STRICT_DEFAULT,
            single_trade_pct_max=SINGLE_TRADE_PCT_STRICT_DEFAULT,
            daily_trade_pct_max=DAILY_TRADE_PCT_STRICT_DEFAULT,
            cooldown_seconds=COOLDOWN_STRICT_DEFAULT_SECONDS,
            is_custom=False,
            expires_on=None,
        )

    expires_on = _parse_date(os.getenv("CUSTOM_LIMITER_EXPIRES_ON"))
    if _is_expired(expires_on):
        logger.warning(
            "risk_limiter: CUSTOM_LIMITER_EXPIRES_ON=%s has passed; reverting to strict limits",
            expires_on,
        )
        return EffectiveLimits(
            hf_min=HF_STRICT_DEFAULT,
            single_trade_pct_max=SINGLE_TRADE_PCT_STRICT_DEFAULT,
            daily_trade_pct_max=DAILY_TRADE_PCT_STRICT_DEFAULT,
            cooldown_seconds=COOLDOWN_STRICT_DEFAULT_SECONDS,
            is_custom=False,
            expires_on=expires_on,
        )

    # Parse custom values and enforce hard limits
    raw_hf = _parse_decimal(os.getenv("CUSTOM_HF_MIN"), HF_STRICT_DEFAULT)
    raw_single = _parse_decimal(
        os.getenv("CUSTOM_SINGLE_TRADE_PCT"), SINGLE_TRADE_PCT_STRICT_DEFAULT
    )
    raw_daily = _parse_decimal(os.getenv("CUSTOM_DAILY_TRADE_PCT"), DAILY_TRADE_PCT_STRICT_DEFAULT)
    raw_cooldown = _parse_int(os.getenv("CUSTOM_COOLDOWN_SECONDS"), COOLDOWN_STRICT_DEFAULT_SECONDS)

    hf_min = max(raw_hf, HF_HARD_MIN)
    single_pct = min(raw_single, SINGLE_TRADE_PCT_HARD_MAX)
    daily_pct = min(raw_daily, DAILY_TRADE_PCT_HARD_MAX)
    cooldown = max(raw_cooldown, COOLDOWN_HARD_MIN_SECONDS)

    limits = EffectiveLimits(
        hf_min=hf_min,
        single_trade_pct_max=single_pct,
        daily_trade_pct_max=daily_pct,
        cooldown_seconds=cooldown,
        is_custom=True,
        expires_on=expires_on,
    )

    logger.warning(
        "risk_limiter: CUSTOM limits ACTIVE — HF_MIN=%s, single=%s%%, daily=%s%%, "
        "cooldown=%ds, expires=%s",
        hf_min,
        single_pct,
        daily_pct,
        cooldown,
        expires_on,
    )

    return limits


def notify_slack_if_custom(limits: EffectiveLimits) -> None:
    """Post a Slack warning when custom limits are active on startup.

    Call this once from app startup (e.g., main.py lifespan). No-op when
    SLACK_WEBHOOK_URL is unset or limits.is_custom is False.
    """
    if not limits.is_custom:
        return

    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.debug("risk_limiter: SLACK_WEBHOOK_URL not set; skipping Slack notification")
        return

    import json  # noqa: PLC0415

    message = (
        f":warning: *[risk_limiter] CUSTOM limits ACTIVE on `{os.getenv('APP_ENV', 'unknown')}` env*\n"
        f"HF_MIN={limits.hf_min} | single={limits.single_trade_pct_max}% | "
        f"daily={limits.daily_trade_pct_max}% | cooldown={limits.cooldown_seconds}s | "
        f"expires={limits.expires_on}"
    )
    payload = json.dumps({"text": message}).encode("utf-8")

    try:
        req = urllib.request.Request(  # noqa: S310
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            if resp.status != 200:
                logger.warning("risk_limiter: Slack notification returned status %d", resp.status)
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk_limiter: Slack notification failed: %s", exc)
