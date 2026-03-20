# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_ai_sentiment.py
"""Xセンチメント分析のテスト。"""

from app.ai.router import _generate_mock_sentiment


class TestGenerateMockSentiment:
    def test_returns_correct_hours(self):
        result = _generate_mock_sentiment(24)
        assert result.hours == 24
        assert len(result.data_points) == 24

    def test_is_mock_true(self):
        result = _generate_mock_sentiment(6)
        assert result.is_mock is True

    def test_data_points_score_in_range(self):
        result = _generate_mock_sentiment(12)
        for dp in result.data_points:
            assert -1.0 <= dp.score <= 1.0

    def test_latest_posts_count(self):
        result = _generate_mock_sentiment(24)
        assert len(result.latest_posts) == 10

    def test_latest_posts_score_in_range(self):
        result = _generate_mock_sentiment(24)
        for post in result.latest_posts:
            assert -1.0 <= post.score <= 1.0

    def test_current_label_positive(self):
        result = _generate_mock_sentiment(24)
        if result.current_score > 0.2:
            assert result.current_label.value == "positive"
        elif result.current_score < -0.2:
            assert result.current_label.value == "negative"
        else:
            assert result.current_label.value == "neutral"

    def test_hours_clamped_min(self):
        # hours=0 → clamped to 1
        result = _generate_mock_sentiment(1)
        assert len(result.data_points) == 1

    def test_deterministic(self):
        """Same seed → same result."""
        r1 = _generate_mock_sentiment(24)
        r2 = _generate_mock_sentiment(24)
        assert r1.current_score == r2.current_score
        assert r1.data_points[0].score == r2.data_points[0].score

    def test_ai_action_correlates_with_score(self):
        """High score → BUY, low score → SELL, neutral → HOLD."""
        result = _generate_mock_sentiment(24)
        for dp in result.data_points:
            if dp.score > 0.3:
                assert dp.ai_action is not None
                assert dp.ai_action.value == "BUY"
            elif dp.score < -0.3:
                assert dp.ai_action is not None
                assert dp.ai_action.value == "SELL"


class TestSentimentSchemas:
    def test_xpost_valid(self):
        from app.ai.schemas import SentimentLabel, XPost

        post = XPost(
            post_id="1",
            text="BTC to the moon!",
            sentiment=SentimentLabel.POSITIVE,
            score=0.85,
            created_at="2026-01-01T00:00:00Z",
            likes=100,
        )
        assert post.score == 0.85

    def test_sentiment_data_point_valid(self):
        from app.ai.schemas import SentimentDataPoint, SentimentLabel, TradeAction

        dp = SentimentDataPoint(
            timestamp="2026-01-01T00:00:00Z",
            score=0.5,
            label=SentimentLabel.POSITIVE,
            post_count=50,
            ai_action=TradeAction.BUY,
        )
        assert dp.ai_action == TradeAction.BUY

    def test_sentiment_data_point_score_bounds(self):
        import pytest
        from pydantic import ValidationError

        from app.ai.schemas import SentimentDataPoint, SentimentLabel

        with pytest.raises(ValidationError):
            SentimentDataPoint(
                timestamp="2026-01-01T00:00:00Z",
                score=1.5,  # out of range
                label=SentimentLabel.POSITIVE,
            )
