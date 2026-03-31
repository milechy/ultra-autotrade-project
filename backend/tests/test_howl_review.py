# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for HOWL self-improvement review."""

import tempfile
from decimal import Decimal

import pytest

from app.ai.judgment_log import JudgmentLogger, JudgmentRecord
from app.automation.howl_review import (
    evaluate_judgment,
    run_howl_review,
)


@pytest.fixture
def tmp_log_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def jlogger(tmp_log_dir):
    return JudgmentLogger(log_dir=tmp_log_dir)


class TestEvaluateJudgment:
    def test_hold_during_high_geo_risk_is_correct(self) -> None:
        record = JudgmentRecord(
            action="HOLD", confidence=35, geo_risk_score=75, health_factor="1.72"
        )
        review = evaluate_judgment(record, Decimal("1.70"), current_geo_risk=80)
        assert review.was_correct is True
        assert "prudent" in review.reason_correct.lower()

    def test_buy_with_stable_hf_is_correct(self) -> None:
        record = JudgmentRecord(action="BUY", confidence=80, health_factor="1.72")
        review = evaluate_judgment(record, Decimal("1.75"), current_geo_risk=30)
        assert review.was_correct is True
        assert (
            "stable" in review.reason_correct.lower() or "improved" in review.reason_correct.lower()
        )

    def test_sell_before_hf_drop_is_correct(self) -> None:
        record = JudgmentRecord(action="SELL", confidence=70, health_factor="1.72")
        review = evaluate_judgment(record, Decimal("1.50"), current_geo_risk=40)
        assert review.was_correct is True
        assert "dropped" in review.reason_correct.lower()

    def test_hold_without_hf_data_is_inconclusive(self) -> None:
        record = JudgmentRecord(action="HOLD", confidence=50, geo_risk_score=30)
        review = evaluate_judgment(record, None, current_geo_risk=25)
        assert review.was_correct is None
        assert "inconclusive" in review.reason_correct.lower()

    def test_sell_during_rising_geo_risk(self) -> None:
        record = JudgmentRecord(action="SELL", confidence=65, health_factor="1.80")
        review = evaluate_judgment(record, Decimal("1.82"), current_geo_risk=75)
        assert review.was_correct is True
        assert "geo risk" in review.reason_correct.lower()

    def test_hf_improved_flag_set_correctly(self) -> None:
        record = JudgmentRecord(action="HOLD", confidence=50, health_factor="1.60")
        review = evaluate_judgment(record, Decimal("1.80"), current_geo_risk=20)
        assert review.hf_improved is True

    def test_hf_degraded_flag_set_correctly(self) -> None:
        record = JudgmentRecord(action="HOLD", confidence=50, health_factor="1.80")
        review = evaluate_judgment(record, Decimal("1.60"), current_geo_risk=20)
        assert review.hf_improved is False
        assert review.was_correct is True  # HOLD was correct — HF dropped


class TestRunHOWLReview:
    @pytest.mark.asyncio
    async def test_empty_review(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        report = await run_howl_review(judgment_logger=jlogger)
        assert report.judgments_reviewed == 0
        assert "No judgments" in report.summary

    @pytest.mark.asyncio
    async def test_review_with_judgments(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        await jlogger.record(
            JudgmentRecord(action="HOLD", confidence=35, geo_risk_score=75, health_factor="1.72")
        )
        await jlogger.record(JudgmentRecord(action="BUY", confidence=80, health_factor="1.72"))

        report = await run_howl_review(
            judgment_logger=jlogger,
            current_hf=Decimal("1.75"),
        )
        assert report.judgments_reviewed == 2
        assert report.correct_count >= 1

    @pytest.mark.asyncio
    async def test_excessive_hold_recommendation(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        for _ in range(9):
            await jlogger.record(JudgmentRecord(action="HOLD", confidence=30))
        await jlogger.record(JudgmentRecord(action="BUY", confidence=80))

        report = await run_howl_review(judgment_logger=jlogger)
        hold_recs = [r for r in report.recommendations if "conservative" in r.lower()]
        assert len(hold_recs) >= 1

    @pytest.mark.asyncio
    async def test_win_rate_calculation(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        for _ in range(3):
            await jlogger.record(JudgmentRecord(action="HOLD", confidence=35, geo_risk_score=80))
        report = await run_howl_review(
            judgment_logger=jlogger,
            current_hf=Decimal("1.70"),
        )
        assert report.win_rate == 1.0

    @pytest.mark.asyncio
    async def test_summary_includes_counts(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        await jlogger.record(JudgmentRecord(action="HOLD", confidence=35, geo_risk_score=80))
        report = await run_howl_review(judgment_logger=jlogger)
        assert "1" in report.summary
        assert "correct" in report.summary

    @pytest.mark.asyncio
    async def test_high_risk_buy_recommendation(self, jlogger: JudgmentLogger) -> None:
        await jlogger.initialize()
        await jlogger.record(
            JudgmentRecord(action="BUY", confidence=80, geo_risk_score=65, health_factor="1.72")
        )
        report = await run_howl_review(
            judgment_logger=jlogger,
            current_hf=Decimal("1.75"),
        )
        risky_buys = [r for r in report.recommendations if "geo risk" in r.lower()]
        assert len(risky_buys) >= 1
