# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/api/alias_router.py
"""API エイリアス — /api/safety-score など透過的エイリアス。"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_viewer

router = APIRouter(tags=["api"])


@router.get("/api/safety-score", summary="安全スコアを取得する")
def get_safety_score(_: object = Depends(require_viewer)) -> dict[str, Any]:
    """Return safety score (alias of /api/transparency/safety-score)."""
    from app.aave.safety_score import SafetyScoreCalculator, SafetyScoreParams  # noqa: PLC0415

    params = SafetyScoreParams(
        utilization_rate=Decimal("0.50"),
        health_factor=Decimal("0"),
        volatility_30d=Decimal("0.15"),
    )
    result = SafetyScoreCalculator().calculate(params)
    return result.model_dump()
