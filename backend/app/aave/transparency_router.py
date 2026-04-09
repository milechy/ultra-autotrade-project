# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Transparency Router — /api/transparency endpoints.

Exposes safety score, explanation, signal, impact, simulation,
performance, and risk-profile data without requiring a database session.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.aave.impact_calculator import ImpactCalculator, ImpactParams
from app.aave.risk_profile import RiskProfileManager
from app.aave.safety_score import SafetyScoreCalculator, SafetyScoreParams
from app.aave.simulation_service import SimulationParams, SimulationService
from app.ai.explanation_service import ExplanationContext, ExplanationService
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/transparency", tags=["transparency"])

# ── Default context used by explanation endpoints ────────────────────────────

_DEFAULT_CONTEXT = ExplanationContext(
    action="HOLD",
    utilization_rate=Decimal("0.50"),
    supply_apy=Decimal("0.035"),
    volatility_30d=Decimal("0.15"),
    impact_with=Decimal("5.00"),
    impact_without=Decimal("3.00"),
    impact_difference=Decimal("2.00"),
    asset_symbol="USDC",
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _risk_profile_to_dict(profile: Any) -> dict[str, Any]:
    """Convert RiskProfile dataclass to a JSON-serialisable dict."""
    d = dataclasses.asdict(profile)
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}


# ── 1. Safety Score ──────────────────────────────────────────────────────────


@router.get("/safety-score")
def get_safety_score(_: object = Depends(get_current_user)) -> dict[str, Any]:
    """Return a safety score using fallback market parameters."""
    params = SafetyScoreParams(
        utilization_rate=Decimal("0.50"),  # 50 %
        health_factor=Decimal("0"),  # no position
        volatility_30d=Decimal("0.15"),  # 15 %
    )
    result = SafetyScoreCalculator().calculate(params)
    return result.model_dump()


# ── 2. Explanation (5-step) ──────────────────────────────────────────────────


@router.get("/explanation/{decision_id}")
def get_explanation(decision_id: str) -> dict[str, Any]:
    """Return a 5-step natural-language explanation for a decision."""
    result = ExplanationService().generate(_DEFAULT_CONTEXT)
    return {"decision_id": decision_id, **result.model_dump()}


# ── 3. Signal ────────────────────────────────────────────────────────────────


@router.get("/signal")
def get_signal() -> dict[str, Any]:
    """Return the current market signal (weather metaphor)."""
    result = ExplanationService().generate_signal(_DEFAULT_CONTEXT)
    return result.model_dump()


# ── 4. Impact ────────────────────────────────────────────────────────────────


@router.get("/impact")
def get_impact(current_amount: float = 1000.0, action_amount: float = 500.0) -> dict[str, Any]:
    """Return gain/loss impact for a proposed deposit action.

    Query params:
        current_amount: Current balance in USD (default 1000).
        action_amount:  Amount to deposit in USD (default 500, must be > 0).
    """
    if action_amount <= 0:
        raise HTTPException(status_code=422, detail="action_amount must be greater than 0")

    calc = ImpactCalculator()
    params = ImpactParams(
        current_balance_usd=Decimal(str(current_amount)),
        current_apy=Decimal("0.035"),
        proposed_apy=Decimal("0.055"),
        action_amount_usd=Decimal(str(action_amount)),
        days=30,
    )
    result = calc.calculate_impact(params)
    formatted = calc.format_comparison(result)
    return {
        "impact": result.model_dump(),
        "formatted": formatted.model_dump(),
    }


# ── 5. Simulation ────────────────────────────────────────────────────────────


@router.get("/simulation")
def get_simulation() -> dict[str, Any]:
    """Return supply / withdraw / hold scenario projections."""
    params = SimulationParams(
        current_balance_usd=Decimal("10000"),
        current_apy=Decimal("0.035"),
        proposed_apy=Decimal("0.055"),
        additional_amount_usd=Decimal("3000"),
        gas_cost_usd=Decimal("2.0"),
        days=30,
    )
    result = SimulationService().simulate(params)
    return result.model_dump()


# ── 6. Performance ───────────────────────────────────────────────────────────


@router.get("/performance")
def get_performance() -> dict[str, Any]:
    """Return performance summary. Returns nulls when no real data is available."""
    return {
        "total_trades": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": None,
        "total_pnl_jpy": None,
        "avg_pnl_per_trade_jpy": None,
        "period_days": 30,
    }


@router.get("/performance/monthly")
def get_performance_monthly() -> list[dict[str, Any]]:
    """Return monthly P&L data. Returns empty list when no real data is available."""
    return []


# ── 7. Risk Profiles (list) ──────────────────────────────────────────────────


@router.get("/risk-profile")
def list_risk_profiles() -> dict[str, Any]:
    """Return all three risk profiles (conservative, balanced, aggressive)."""
    mgr = RiskProfileManager()
    profiles = [
        _risk_profile_to_dict(mgr.get_profile(mode))
        for mode in ("conservative", "balanced", "aggressive")
    ]
    return {"profiles": profiles}


# ── 8. Risk Profile (single) ─────────────────────────────────────────────────


@router.get("/risk-profile/{mode}")
def get_risk_profile(mode: str) -> dict[str, Any]:
    """Return a single risk profile; falls back to conservative for unknown modes."""
    profile = RiskProfileManager().get_profile(mode)
    return _risk_profile_to_dict(profile)
