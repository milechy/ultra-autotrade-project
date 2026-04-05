# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/exchange/copy_trading.py
"""
Copy Trading API.

Strategyists publish trading strategies; followers subscribe and auto-copy.

In-memory storage for PoC phase — resets on process restart.

Endpoints:
  GET    /exchange/strategies                         — list public strategies
  GET    /exchange/strategies/{strategy_id}           — strategy detail + performance
  POST   /exchange/strategies                         — register strategy (strategist)
  POST   /exchange/strategies/{strategy_id}/subscribe — subscribe (follower)
  DELETE /exchange/strategies/{strategy_id}/subscribe — unsubscribe
  PUT    /exchange/subscriptions/{subscription_id}/ratio — update copy ratio
  GET    /exchange/subscriptions                      — list follower's subscriptions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(tags=["copy-trading"])  # no prefix — included by exchange router


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Strategy risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Strategy(BaseModel):
    """A published trading strategy created by a strategist."""

    id: str = Field(..., description="Unique strategy ID.")
    name: str = Field(..., description="Strategy display name.")
    description: str = Field(..., description="Strategy description.")
    risk_level: RiskLevel = Field(..., description="Risk classification.")
    strategist_id: str = Field(..., description="Creator's user ID.")
    is_public: bool = Field(True, description="Whether the strategy is publicly visible.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")


class StrategyPerformance(BaseModel):
    """Computed performance metrics for a strategy."""

    strategy_id: str = Field(..., description="Associated strategy ID.")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="Win rate (0.0 – 1.0).")
    sharpe_ratio: float = Field(..., description="Annualised Sharpe ratio.")
    total_pnl: Decimal = Field(..., description="Cumulative PnL in USDT.")
    total_trades: int = Field(..., ge=0, description="Total number of trades.")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC).")


class StrategyWithPerformance(Strategy):
    """Strategy combined with its latest performance metrics."""

    performance: Optional[StrategyPerformance] = None


class CopySubscription(BaseModel):
    """A follower's subscription to a strategy."""

    id: str = Field(..., description="Unique subscription ID.")
    strategy_id: str = Field(..., description="Followed strategy ID.")
    follower_id: str = Field(..., description="Follower's user ID.")
    copy_ratio: float = Field(
        ..., gt=0.0, le=1.0, description="Fraction of strategist's order size to copy."
    )
    is_active: bool = Field(True, description="Whether the subscription is active.")
    created_at: datetime = Field(..., description="Subscription creation timestamp (UTC).")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., max_length=500)
    risk_level: RiskLevel
    strategist_id: str = Field(..., min_length=1)


class SubscribeRequest(BaseModel):
    follower_id: str = Field(..., min_length=1)
    copy_ratio: float = Field(..., gt=0.0, le=1.0)


class UpdateRatioRequest(BaseModel):
    copy_ratio: float = Field(..., gt=0.0, le=1.0)


# ---------------------------------------------------------------------------
# In-memory storage (PoC — resets on restart)
# ---------------------------------------------------------------------------

_strategies: dict[str, Strategy] = {}
_performance: dict[str, StrategyPerformance] = {}
_subscriptions: dict[str, CopySubscription] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/strategies",
    response_model=list[StrategyWithPerformance],
    summary="List public strategies sorted by Sharpe ratio",
)
def list_strategies() -> list[StrategyWithPerformance]:
    """Return all public strategies with performance data, sorted by Sharpe ratio desc."""
    results = []
    for s in _strategies.values():
        if s.is_public:
            perf = _performance.get(s.id)
            results.append(StrategyWithPerformance(**s.model_dump(), performance=perf))
    results.sort(
        key=lambda x: x.performance.sharpe_ratio if x.performance else float("-inf"),  # float OK
        reverse=True,
    )
    return results


@router.get(
    "/strategies/{strategy_id}",
    response_model=StrategyWithPerformance,
    summary="Get strategy detail and performance",
)
def get_strategy(strategy_id: str) -> StrategyWithPerformance:
    """Return a single strategy with its performance metrics."""
    strategy = _strategies.get(strategy_id)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy '{strategy_id}' not found.",
        )
    perf = _performance.get(strategy_id)
    return StrategyWithPerformance(**strategy.model_dump(), performance=perf)


@router.post(
    "/strategies",
    response_model=Strategy,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new strategy (strategist)",
)
def create_strategy(body: CreateStrategyRequest) -> Strategy:
    """Create and publish a new copy trading strategy."""
    strategy = Strategy(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        risk_level=body.risk_level,
        strategist_id=body.strategist_id,
        is_public=True,
        created_at=_now(),
    )
    _strategies[strategy.id] = strategy
    return strategy


@router.post(
    "/strategies/{strategy_id}/subscribe",
    response_model=CopySubscription,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a strategy (follower)",
)
def subscribe_strategy(strategy_id: str, body: SubscribeRequest) -> CopySubscription:
    """Subscribe a follower to a strategy. Only one active subscription per strategy per follower."""
    if strategy_id not in _strategies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy '{strategy_id}' not found.",
        )
    # Check for existing active subscription
    for sub in _subscriptions.values():
        if sub.strategy_id == strategy_id and sub.follower_id == body.follower_id and sub.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already subscribed to this strategy.",
            )
    subscription = CopySubscription(
        id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        follower_id=body.follower_id,
        copy_ratio=body.copy_ratio,
        is_active=True,
        created_at=_now(),
    )
    _subscriptions[subscription.id] = subscription
    return subscription


@router.delete(
    "/strategies/{strategy_id}/subscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsubscribe from a strategy",
)
def unsubscribe_strategy(strategy_id: str, follower_id: str) -> None:
    """Deactivate all active subscriptions for this follower + strategy."""
    found = False
    for sub in _subscriptions.values():
        if sub.strategy_id == strategy_id and sub.follower_id == follower_id and sub.is_active:
            sub.is_active = False
            found = True
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found.",
        )


@router.put(
    "/subscriptions/{subscription_id}/ratio",
    response_model=CopySubscription,
    summary="Update copy ratio for a subscription",
)
def update_subscription_ratio(subscription_id: str, body: UpdateRatioRequest) -> CopySubscription:
    """Update the copy ratio of an existing active subscription."""
    sub = _subscriptions.get(subscription_id)
    if sub is None or not sub.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active subscription '{subscription_id}' not found.",
        )
    updated = CopySubscription(
        id=sub.id,
        strategy_id=sub.strategy_id,
        follower_id=sub.follower_id,
        copy_ratio=body.copy_ratio,
        is_active=sub.is_active,
        created_at=sub.created_at,
    )
    _subscriptions[subscription_id] = updated
    return updated


@router.get(
    "/subscriptions",
    response_model=list[CopySubscription],
    summary="List active subscriptions (follower view)",
)
def list_subscriptions(follower_id: str) -> list[CopySubscription]:
    """Return all active subscriptions for a given follower."""
    return [s for s in _subscriptions.values() if s.follower_id == follower_id and s.is_active]
