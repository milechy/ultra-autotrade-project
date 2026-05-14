# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/health/detail_router.py
"""GET /health/detail — 4-axis multi-layer health (admin only).

Reads cached probe state from health/probes.py and computes
warnings/status from cross_judgment DB stats and risk_limiter state.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai.models import AIDecision
from app.auth.dependencies import require_admin
from app.auth.models import User
from app.database import get_db
from app.health.cache import get_health_detail_cache
from app.health.probes import (
    get_openai_status,
    get_oracle_fresh,
    get_perplexity_status,
    get_reserve_healthy,
)
from app.health.schemas import (
    CrossJudgmentHealth,
    HealthComponents,
    HealthDetailResponse,
    QuotaHealth,
    SafetyHealth,
    SchedulerHealth,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_SCHEDULER_STALL_THRESHOLD_MINUTES = 300


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_scheduler() -> SchedulerHealth:
    from app.automation.ai_judgment_scheduler import get_scheduler_status  # noqa: PLC0415
    from app.automation.scheduler_watchdog import compute_scheduler_health  # noqa: PLC0415

    status = get_scheduler_status()
    interval_hours = int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS", "4"))
    health = compute_scheduler_health(status.get("last_run"), interval_hours)

    last_run = _parse_iso(status.get("last_run"))
    next_run = _parse_iso(status.get("next_run"))

    minutes_since_last: Optional[int] = None
    if last_run is not None:
        delta = datetime.now(timezone.utc) - last_run
        minutes_since_last = int(delta.total_seconds() / 60)

    return SchedulerHealth(
        ok=bool(health.get("healthy")) and bool(status.get("running")),
        last_judgment=last_run,
        next_judgment=next_run,
        minutes_since_last=minutes_since_last,
    )


def _build_quota() -> QuotaHealth:
    openai = get_openai_status()
    perplexity = get_perplexity_status()
    return QuotaHealth(
        ok=openai.reachable and perplexity.reachable,
        openai=openai,
        perplexity=perplexity,
    )


def _build_cross_judgment(db: Session) -> CrossJudgmentHealth:
    six_hours_ago = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta  # noqa: PLC0415

    six_hours_ago = six_hours_ago - timedelta(hours=6)

    total = (
        db.scalar(select(func.count(AIDecision.id)).where(AIDecision.created_at >= six_hours_ago))
        or 0
    )
    has_secondary = (
        db.scalar(
            select(func.count(AIDecision.id)).where(
                and_(
                    AIDecision.created_at >= six_hours_ago,
                    AIDecision.secondary_provider.isnot(None),
                )
            )
        )
        or 0
    )
    agreed_true = (
        db.scalar(
            select(func.count(AIDecision.id)).where(
                and_(
                    AIDecision.created_at >= six_hours_ago,
                    AIDecision.agreed.is_(True),
                    AIDecision.secondary_provider.isnot(None),
                )
            )
        )
        or 0
    )
    agreed_false = (
        db.scalar(
            select(func.count(AIDecision.id)).where(
                and_(
                    AIDecision.created_at >= six_hours_ago,
                    AIDecision.agreed.is_(False),
                    AIDecision.secondary_provider.isnot(None),
                )
            )
        )
        or 0
    )

    return CrossJudgmentHealth(
        ok=total > 0 and has_secondary > 0,
        last_6h_total=int(total),
        has_secondary_count=int(has_secondary),
        agreed_true_count=int(agreed_true),
        agreed_false_count=int(agreed_false),
    )


def _build_safety() -> SafetyHealth:
    from app.aave.risk_limiter import get_effective_limits  # noqa: PLC0415
    from app.automation.state import get_monitoring_service  # noqa: PLC0415

    limits = get_effective_limits()
    stress_paused = not get_monitoring_service().is_trading_allowed()

    oracle_fresh = get_oracle_fresh()
    reserve_healthy = get_reserve_healthy()

    expires_on: Optional[date] = limits.expires_on if limits.is_custom else None
    expires_in_days: Optional[int] = None
    if expires_on is not None:
        expires_in_days = (expires_on - date.today()).days

    return SafetyHealth(
        ok=oracle_fresh and reserve_healthy and not stress_paused,
        oracle_fresh=oracle_fresh,
        reserve_healthy=reserve_healthy,
        stress_paused=stress_paused,
        limiter_mode="custom" if limits.is_custom else "strict",
        limiter_expires_on=expires_on,
        limiter_expires_in_days=expires_in_days,
    )


def _compute_warnings(components: HealthComponents) -> list[str]:
    warnings: list[str] = []
    s = components.scheduler
    if (
        s.minutes_since_last is not None
        and s.minutes_since_last > _SCHEDULER_STALL_THRESHOLD_MINUTES
    ):
        warnings.append("scheduler_stalled")
    if components.quota.openai.last_error == "quota_exceeded":
        warnings.append("openai_quota_exceeded")
    if components.quota.perplexity.last_error == "quota_exceeded":
        warnings.append("perplexity_quota_exceeded")
    if not components.cross_judgment.ok:
        warnings.append("cross_judgment_inactive")
    if components.safety.limiter_expires_in_days is not None:
        days = components.safety.limiter_expires_in_days
        if days <= 0:
            warnings.append("limiter_expired_using_strict")
        elif days <= 2:
            warnings.append(f"limiter_expires_soon_{days}_days")
    return warnings


def _compute_status(components: HealthComponents) -> str:
    if not components.scheduler.ok:
        return "down"
    if components.quota.ok and components.cross_judgment.ok and components.safety.ok:
        return "ok"
    return "degraded"


def build_health_detail(db: Session) -> HealthDetailResponse:
    """Build a HealthDetailResponse from current probe state and DB.

    Synchronous helper used by both the populator and tests.
    """
    components = HealthComponents(
        scheduler=_build_scheduler(),
        quota=_build_quota(),
        cross_judgment=_build_cross_judgment(db),
        safety=_build_safety(),
    )
    warnings = _compute_warnings(components)
    status = _compute_status(components)
    return HealthDetailResponse(
        status=status,
        components=components,
        warnings=warnings,
        cached_at=datetime.now(timezone.utc),
    )


@router.get("/health/detail", response_model=HealthDetailResponse)
async def get_health_detail(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> HealthDetailResponse:
    """Return multi-layer health detail (admin only, 5min cache)."""
    cache = get_health_detail_cache()

    async def _populate() -> HealthDetailResponse:
        return build_health_detail(db)

    return await cache.get_or_populate(_populate)
