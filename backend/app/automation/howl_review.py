# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
HOWL — Nightly Self-Improvement Review (Nunchi pattern).

Every N hours, reviews past AI judgments against actual market outcomes:
  1. Fetches recent judgments from JudgmentLogger
  2. Compares judgment-time context vs current market state
  3. Marks each judgment as correct/incorrect
  4. Updates CognitiveState win_rate
  5. Generates improvement summary for Slack notification

Architecture:
  - Runs as background task (default: every 6 hours)
  - Reads from JudgmentLogger (JSONL)
  - Reads current market state from data feed caches
  - Updates outcomes via JudgmentLogger.update_outcome()
  - Generates human-readable review report

Note: APY-based evaluation will be added when get_supply_apy() is implemented in Aave client.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.judgment_log import JudgmentLogger, JudgmentRecord, get_judgment_logger
from app.data_feeds.geopolitical import get_cached_geo_risk

logger = logging.getLogger(__name__)


# ============================================================
# Schemas
# ============================================================
class JudgmentReview(BaseModel):
    """Review result for a single past judgment."""

    timestamp: datetime
    action: str
    confidence: int
    was_correct: Optional[bool] = None
    reason_correct: str = ""
    hf_at_judgment: Optional[str] = None
    hf_now: Optional[str] = None
    hf_improved: Optional[bool] = None
    geo_risk_at_judgment: Optional[int] = None
    geo_risk_now: Optional[int] = None


class HOWLReport(BaseModel):
    """Summary of a HOWL review cycle."""

    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    judgments_reviewed: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    inconclusive_count: int = 0
    win_rate: Optional[float] = None
    summary: str = ""
    reviews: list[JudgmentReview] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ============================================================
# Review Logic
# ============================================================
def evaluate_judgment(
    record: JudgmentRecord,
    current_hf: Optional[Decimal],
    current_geo_risk: int,
) -> JudgmentReview:
    """Evaluate whether a past judgment was correct.

    Heuristics:
      - BUY was correct if HF remained stable or improved (no liquidation risk)
      - SELL was correct if HF dropped after judgment (early exit was wise)
      - HOLD was correct if geo risk was high or HF would have dropped
      - Inconclusive when insufficient data (no HF comparison available)

    APY-based evaluation will be added when get_supply_apy() is implemented.
    """
    review = JudgmentReview(
        timestamp=record.timestamp,
        action=record.action,
        confidence=record.confidence,
        hf_at_judgment=record.health_factor,
        hf_now=str(current_hf) if current_hf is not None else None,
        geo_risk_at_judgment=record.geo_risk_score,
        geo_risk_now=current_geo_risk,
    )

    # Evaluate HF change
    if record.health_factor and current_hf is not None:
        try:
            hf_then = Decimal(record.health_factor)
            review.hf_improved = current_hf >= hf_then
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not parse health_factor for HF comparison: %s", exc)

    if record.action == "HOLD":
        if record.geo_risk_score is not None and record.geo_risk_score >= 60:
            review.was_correct = True
            review.reason_correct = "HOLD during high geo risk was prudent"
        elif review.hf_improved is False:
            review.was_correct = True
            review.reason_correct = "HOLD was correct — HF dropped, action would have been risky"
        elif (
            review.hf_improved is True and record.confidence is not None and record.confidence < 40
        ):
            review.was_correct = True
            review.reason_correct = "Low confidence HOLD was appropriate"
        elif (
            review.hf_improved is True
            and record.geo_risk_score is not None
            and record.geo_risk_score < 30
        ):
            review.was_correct = False
            review.reason_correct = (
                "HOLD during low risk + improving HF — missed opportunity to act"
            )
        else:
            review.was_correct = None
            review.reason_correct = "Inconclusive — APY data not yet available for evaluation"

    elif record.action == "BUY":
        if review.hf_improved is True:
            review.was_correct = True
            review.reason_correct = "BUY was correct — HF stable or improved"
        elif review.hf_improved is False:
            hf_drop = (hf_then - current_hf) if current_hf is not None else Decimal("0")
            if hf_drop > Decimal("0.3"):
                review.was_correct = False
                review.reason_correct = (
                    f"BUY was incorrect — HF dropped by {hf_drop} (significant deterioration)"
                )
            else:
                review.was_correct = None
                review.reason_correct = (
                    "HF dropped slightly after BUY — inconclusive without APY data"
                )
        else:
            review.was_correct = None
            review.reason_correct = "Inconclusive — no HF comparison available"

    elif record.action == "SELL":
        if review.hf_improved is False:
            review.was_correct = True
            review.reason_correct = "SELL was correct — HF dropped, early exit was wise"
        elif current_geo_risk >= 70:
            review.was_correct = True
            review.reason_correct = "SELL during rising geo risk was prudent"
        elif review.hf_improved is True and current_geo_risk < 40:
            review.was_correct = False
            review.reason_correct = "SELL was premature — HF improved and geo risk remained low"
        else:
            review.was_correct = None
            review.reason_correct = "Inconclusive — need more market data"

    return review


async def run_howl_review(
    judgment_logger: Optional[JudgmentLogger] = None,
    current_hf: Optional[Decimal] = None,
    review_count: int = 10,
) -> HOWLReport:
    """Run HOWL review cycle.

    1. Get recent judgments
    2. Evaluate each against market state
    3. Update outcomes in JudgmentLogger
    4. Generate report with recommendations
    """
    jlog = judgment_logger or get_judgment_logger()
    geo_risk = get_cached_geo_risk()

    recent = jlog.get_recent_judgments(review_count)
    if not recent:
        return HOWLReport(summary="No judgments to review.")

    report = HOWLReport()
    report.judgments_reviewed = len(recent)

    for record in recent:
        review = evaluate_judgment(record, current_hf, geo_risk.geo_risk_score)
        report.reviews.append(review)

        if review.was_correct is not None:
            await jlog.update_outcome(
                timestamp=record.timestamp,
                was_correct=review.was_correct,
                hf_change=f"{review.hf_at_judgment} → {review.hf_now}" if review.hf_now else None,
            )

        if review.was_correct is True:
            report.correct_count += 1
        elif review.was_correct is False:
            report.incorrect_count += 1
        else:
            report.inconclusive_count += 1

    evaluated = report.correct_count + report.incorrect_count
    if evaluated > 0:
        report.win_rate = report.correct_count / evaluated

    if report.incorrect_count > report.correct_count:
        report.recommendations.append(
            "AI judgment accuracy is below 50%. "
            "Consider reviewing prompt templates and risk thresholds."
        )

    hold_count = sum(1 for r in report.reviews if r.action == "HOLD")
    if hold_count > len(report.reviews) * 0.8:
        report.recommendations.append(
            f"AI is overly conservative: {hold_count}/{len(report.reviews)} judgments were HOLD. "
            "Consider lowering confidence thresholds or adjusting risk parameters."
        )

    high_risk_buys = [
        r
        for r in report.reviews
        if r.action == "BUY" and r.geo_risk_at_judgment is not None and r.geo_risk_at_judgment >= 60
    ]
    if high_risk_buys:
        report.recommendations.append(
            f"{len(high_risk_buys)} BUY judgment(s) made during high geo risk. "
            "Review whether geo_risk_score threshold for BUY suppression needs adjustment."
        )

    report.summary = (
        f"Reviewed {report.judgments_reviewed} judgments: "
        f"{report.correct_count} correct, {report.incorrect_count} incorrect, "
        f"{report.inconclusive_count} inconclusive."
    )
    if report.win_rate is not None:
        report.summary += f" Win rate: {report.win_rate:.0%}."
    if report.recommendations:
        report.summary += f" {len(report.recommendations)} recommendation(s) generated."

    logger.info("HOWL review: %s", report.summary)
    return report


# ============================================================
# Background Task
# ============================================================
async def start_howl_background_task(interval_hours: int = 6) -> None:
    """Background loop that runs HOWL review periodically."""
    logger.info("Starting HOWL review background task (every %dh)", interval_hours)
    await asyncio.sleep(300)  # 5 min warm-up: let data feeds populate
    while True:
        try:
            report = await run_howl_review()
            if report.recommendations:
                logger.warning("HOWL recommendations: %s", report.recommendations)
        except Exception as exc:
            logger.error("HOWL review failed: %s", exc)
        await asyncio.sleep(interval_hours * 3600)
