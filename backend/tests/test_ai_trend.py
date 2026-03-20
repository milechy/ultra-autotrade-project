# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""tests/test_ai_trend.py — GET /ai/trend/confidence エンドポイントのテスト"""

from datetime import datetime, timezone

import pytest


class TestGenerateMockTrend:
    """_generate_mock_trend の単体テスト。"""

    def test_returns_correct_count(self) -> None:
        from app.ai.router import _generate_mock_trend

        result = _generate_mock_trend(7)
        assert len(result) == 7 * 3

    def test_confidence_in_range(self) -> None:
        from app.ai.router import _generate_mock_trend

        for dp in _generate_mock_trend(30):
            assert 0.0 <= dp.confidence <= 100.0

    def test_deterministic(self) -> None:
        from app.ai.router import _generate_mock_trend

        first = [dp.confidence for dp in _generate_mock_trend(7)]
        second = [dp.confidence for dp in _generate_mock_trend(7)]
        assert first == second

    def test_actions_are_valid(self) -> None:
        from app.ai.router import _generate_mock_trend
        from app.ai.schemas import TradeAction

        actions = {dp.action for dp in _generate_mock_trend(7)}
        assert actions <= {TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD}


class TestAggregateByVersion:
    """_aggregate_by_version の単体テスト。"""

    def test_groups_correctly(self) -> None:
        from app.ai.router import _aggregate_by_version
        from app.ai.schemas import ConfidenceDataPoint, TradeAction

        data = [
            ConfidenceDataPoint(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=TradeAction.BUY,
                confidence=80.0,
                prompt_version="v1",
            ),
            ConfidenceDataPoint(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=TradeAction.SELL,
                confidence=60.0,
                prompt_version="v1",
            ),
            ConfidenceDataPoint(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=TradeAction.HOLD,
                confidence=50.0,
                prompt_version="v2",
            ),
        ]
        result = _aggregate_by_version(data)
        by_version = {r.version: r for r in result}

        assert "v1" in by_version
        assert "v2" in by_version
        assert by_version["v1"].avg_confidence == 70.0
        assert by_version["v1"].count == 2
        assert by_version["v2"].count == 1

    def test_empty_input(self) -> None:
        from app.ai.router import _aggregate_by_version

        assert _aggregate_by_version([]) == []


class TestConfidenceTrendSchemas:
    """スキーマのバリデーションテスト。"""

    def test_confidence_data_point_valid(self) -> None:
        from app.ai.schemas import ConfidenceDataPoint, TradeAction

        dp = ConfidenceDataPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=TradeAction.BUY,
            confidence=75.5,
            prompt_version="v2",
        )
        assert dp.confidence == 75.5
        assert dp.action == TradeAction.BUY

    def test_confidence_out_of_range(self) -> None:
        from pydantic import ValidationError

        from app.ai.schemas import ConfidenceDataPoint, TradeAction

        with pytest.raises(ValidationError):
            ConfidenceDataPoint(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=TradeAction.BUY,
                confidence=101.0,
                prompt_version="v1",
            )

    def test_prompt_version_summary(self) -> None:
        from app.ai.schemas import PromptVersionSummary

        s = PromptVersionSummary(version="v1", avg_confidence=72.5, count=10)
        assert s.avg_confidence == 72.5

    def test_confidence_trend_response(self) -> None:
        from app.ai.schemas import ConfidenceTrendResponse

        r = ConfidenceTrendResponse(
            data_points=[],
            by_version=[],
            is_mock=True,
            total_count=0,
        )
        assert r.is_mock is True
