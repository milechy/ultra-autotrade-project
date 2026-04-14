# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for HOWL self-improvement review."""

import asyncio
import tempfile
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.ai.judgment_log import JudgmentLogger, JudgmentRecord
from app.automation.howl_review import (
    HOWLReport,
    evaluate_judgment,
    run_howl_review,
)
from app.data_feeds.geopolitical import GeoRiskResult


@pytest.fixture
def tmp_log_dir() -> str:  # type: ignore[misc]
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def jlogger(tmp_log_dir: str) -> JudgmentLogger:
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


# ============================================================
# Additional coverage for uncovered lines
# ============================================================


class TestEvaluateJudgmentAdditional:
    def test_invalid_health_factor_string_does_not_raise(self) -> None:
        """L102-103: 不正な health_factor 文字列 → 警告を出して hf_improved=None のまま継続。"""
        record = JudgmentRecord(
            action="BUY",
            confidence=70,
            health_factor="not-a-number",
        )
        # current_hf を渡して比較しようとするが、parse に失敗しても例外を上げない
        review = evaluate_judgment(record, Decimal("1.75"), current_geo_risk=20)
        assert review.hf_improved is None
        assert review.action == "BUY"

    def test_hold_low_confidence_hf_improved_is_correct(self) -> None:
        """L115-116: HOLD + hf_improved=True + confidence < 40 → correct (低確信度 HOLD は適切)。"""
        record = JudgmentRecord(
            action="HOLD",
            confidence=30,  # < 40
            health_factor="1.70",
            geo_risk_score=None,  # high geo risk ブランチを回避
        )
        review = evaluate_judgment(record, Decimal("1.80"), current_geo_risk=20)
        assert review.hf_improved is True
        assert review.was_correct is True
        assert "low confidence" in review.reason_correct.lower()

    def test_hold_low_geo_risk_hf_improved_is_incorrect(self) -> None:
        """L122-123: HOLD + hf_improved=True + geo_risk_score < 30 → was_correct=False (機会損失)。"""
        record = JudgmentRecord(
            action="HOLD",
            confidence=70,  # >= 40 で「low confidence」ブランチを回避
            health_factor="1.70",
            geo_risk_score=20,  # < 30
        )
        review = evaluate_judgment(record, Decimal("1.85"), current_geo_risk=15)
        assert review.hf_improved is True
        assert review.was_correct is False
        assert "missed opportunity" in review.reason_correct.lower()

    def test_buy_hf_drop_large_is_incorrect(self) -> None:
        """L135-140: BUY + hf_improved=False + HF 低下 > 0.3 → was_correct=False。"""
        record = JudgmentRecord(
            action="BUY",
            confidence=80,
            health_factor="2.00",  # hf_then
        )
        # current_hf = 1.60 → hf_drop = 2.00 - 1.60 = 0.40 > 0.3
        review = evaluate_judgment(record, Decimal("1.60"), current_geo_risk=20)
        assert review.hf_improved is False
        assert review.was_correct is False
        assert "dropped" in review.reason_correct.lower()

    def test_buy_hf_drop_small_is_inconclusive(self) -> None:
        """L141-145: BUY + hf_improved=False + HF 低下 <= 0.3 → inconclusive。"""
        record = JudgmentRecord(
            action="BUY",
            confidence=80,
            health_factor="1.80",
        )
        # current_hf = 1.70 → hf_drop = 0.10 <= 0.3
        review = evaluate_judgment(record, Decimal("1.70"), current_geo_risk=20)
        assert review.hf_improved is False
        assert review.was_correct is None
        assert "inconclusive" in review.reason_correct.lower()

    def test_buy_no_hf_data_is_inconclusive(self) -> None:
        """L147-148: BUY + health_factor なし → inconclusive。"""
        record = JudgmentRecord(
            action="BUY",
            confidence=75,
            health_factor=None,
        )
        review = evaluate_judgment(record, None, current_geo_risk=25)
        assert review.hf_improved is None
        assert review.was_correct is None
        assert "inconclusive" in review.reason_correct.lower()

    def test_sell_hf_improved_low_geo_risk_is_incorrect(self) -> None:
        """L157-162: SELL + hf_improved=True + geo_risk < 40 → was_correct=False (早まった売却)。"""
        record = JudgmentRecord(
            action="SELL",
            confidence=70,
            health_factor="1.70",
        )
        # current_hf = 1.85 > 1.70 → hf_improved=True; geo_risk < 40
        review = evaluate_judgment(record, Decimal("1.85"), current_geo_risk=30)
        assert review.hf_improved is True
        assert review.was_correct is False
        assert "premature" in review.reason_correct.lower()

    def test_sell_no_hf_data_is_inconclusive(self) -> None:
        """SELL + hf データなし + geo_risk < 70 → inconclusive。"""
        record = JudgmentRecord(
            action="SELL",
            confidence=60,
            health_factor=None,
        )
        review = evaluate_judgment(record, None, current_geo_risk=40)
        assert review.was_correct is None
        assert "inconclusive" in review.reason_correct.lower()


class TestRunHOWLReviewAdditional:
    @pytest.mark.asyncio
    async def test_incorrect_count_incremented(self, jlogger: JudgmentLogger) -> None:
        """L203: was_correct=False の判定がある場合に incorrect_count が増加する。"""
        await jlogger.initialize()
        # SELL + hf_improved=True + current_geo_risk < 40 → was_correct=False
        await jlogger.record(
            JudgmentRecord(
                action="SELL",
                confidence=70,
                health_factor="1.70",
                geo_risk_score=25,
            )
        )
        # get_cached_geo_risk を score=25 にモック（デフォルト score=50 では <40 にならない）
        with patch(
            "app.automation.howl_review.get_cached_geo_risk",
            return_value=GeoRiskResult(geo_risk_score=25, summary="Low"),
        ):
            report = await run_howl_review(
                judgment_logger=jlogger,
                current_hf=Decimal("1.90"),  # HF improved → SELL was premature → False
            )
        assert report.incorrect_count >= 1

    @pytest.mark.asyncio
    async def test_win_rate_in_summary(self, jlogger: JudgmentLogger) -> None:
        """L212: win_rate が None でない場合、summary に "Win rate" が含まれる。"""
        await jlogger.initialize()
        # HOLD + high geo_risk → was_correct=True → win_rate 計算あり
        await jlogger.record(JudgmentRecord(action="HOLD", confidence=50, geo_risk_score=80))
        report = await run_howl_review(judgment_logger=jlogger)
        assert report.win_rate is not None
        assert "win rate" in report.summary.lower()

    @pytest.mark.asyncio
    async def test_low_accuracy_recommendation(self, jlogger: JudgmentLogger) -> None:
        """L203 + L212: incorrect > correct のとき、accuracy 低下のレコメンデーションが出る。"""
        await jlogger.initialize()
        # 複数の incorrect 判定（SELL premature: hf_improved=True + geo_risk < 40）
        for _ in range(3):
            await jlogger.record(
                JudgmentRecord(
                    action="SELL",
                    confidence=70,
                    health_factor="1.70",
                    geo_risk_score=20,
                )
            )
        with patch(
            "app.automation.howl_review.get_cached_geo_risk",
            return_value=GeoRiskResult(geo_risk_score=20, summary="Low"),
        ):
            report = await run_howl_review(
                judgment_logger=jlogger,
                current_hf=Decimal("1.95"),  # HF improved → all SELL premature
            )
        # incorrect > correct → recommendation for low accuracy
        accuracy_recs = [r for r in report.recommendations if "50%" in r or "accuracy" in r.lower()]
        assert len(accuracy_recs) >= 1

    @pytest.mark.asyncio
    async def test_recommendations_count_in_summary(self, jlogger: JudgmentLogger) -> None:
        """summary にレコメンデーション件数が含まれる。"""
        await jlogger.initialize()
        # 過度な HOLD でレコメンデーションを生成
        for _ in range(9):
            await jlogger.record(JudgmentRecord(action="HOLD", confidence=30))
        await jlogger.record(JudgmentRecord(action="BUY", confidence=80))
        report = await run_howl_review(judgment_logger=jlogger)
        assert "recommendation" in report.summary.lower()


class TestStartHowlBackgroundTask:
    @pytest.mark.asyncio
    async def test_background_task_runs_once_and_can_be_cancelled(self) -> None:
        """L254-263: バックグラウンドタスクが起動でき、キャンセル可能（fail-open）。"""
        from unittest.mock import AsyncMock

        from app.automation.howl_review import start_howl_background_task

        # asyncio.sleep をモックして即座に通過 → run_howl_review が呼ばれることを確認
        run_mock = AsyncMock(return_value=HOWLReport(summary="ok"))
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            # 2回目の sleep でキャンセルをシミュレート
            if len(sleep_calls) >= 2:
                raise asyncio.CancelledError

        with (
            patch("app.automation.howl_review.run_howl_review", run_mock),
            patch("asyncio.sleep", mock_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await start_howl_background_task(interval_hours=1)

        # run_howl_review が少なくとも 1 回呼ばれた
        assert run_mock.call_count >= 1
        # 最初の sleep は warm-up (300s)
        assert sleep_calls[0] == 300

    @pytest.mark.asyncio
    async def test_background_task_continues_after_exception(self) -> None:
        """L261-262: run_howl_review が例外を上げてもループが止まらない (fail-open)。"""
        from app.automation.howl_review import start_howl_background_task

        call_count = 0

        async def run_side_effect(**kwargs: object) -> HOWLReport:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated failure")
            return HOWLReport(summary="ok")

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 3:
                raise asyncio.CancelledError

        with (
            patch("app.automation.howl_review.run_howl_review", side_effect=run_side_effect),
            patch("asyncio.sleep", mock_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await start_howl_background_task(interval_hours=1)

        # 例外後もループが継続して 2 回目が呼ばれる
        assert call_count >= 2
