# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/health/schemas.py
"""Pydantic models for GET /health/detail (admin)."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SchedulerHealth(BaseModel):
    ok: bool
    last_judgment: Optional[datetime] = None
    next_judgment: Optional[datetime] = None
    minutes_since_last: Optional[int] = None


class ApiQuotaStatus(BaseModel):
    reachable: bool
    last_check: Optional[datetime] = None
    last_error: Optional[Literal["quota_exceeded", "auth_failed", "timeout", "unknown"]] = None


class QuotaHealth(BaseModel):
    ok: bool
    openai: ApiQuotaStatus
    perplexity: ApiQuotaStatus


class CrossJudgmentHealth(BaseModel):
    ok: bool
    last_6h_total: int
    has_secondary_count: int
    agreed_true_count: int
    agreed_false_count: int


class SafetyHealth(BaseModel):
    ok: bool
    oracle_fresh: bool
    reserve_healthy: bool
    stress_paused: bool
    limiter_mode: Literal["strict", "custom"]
    limiter_expires_on: Optional[date] = None
    limiter_expires_in_days: Optional[int] = None


class HealthComponents(BaseModel):
    scheduler: SchedulerHealth
    quota: QuotaHealth
    cross_judgment: CrossJudgmentHealth
    safety: SafetyHealth


class HealthDetailResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    components: HealthComponents
    warnings: list[str] = Field(default_factory=list)
    cached_at: datetime
