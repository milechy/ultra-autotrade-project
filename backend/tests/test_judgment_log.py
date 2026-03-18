"""Tests for AI Judgment Log (Event Log + Cognitive State pattern)."""

import json
import tempfile
from pathlib import Path

import pytest

from app.ai.judgment_log import (
    CognitiveState,
    JudgmentLogger,
    JudgmentRecord,
)


@pytest.fixture
def tmp_log_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def judgment_logger(tmp_log_dir):
    return JudgmentLogger(log_dir=tmp_log_dir)


class TestJudgmentRecord:
    def test_create_record(self) -> None:
        r = JudgmentRecord(action="BUY", confidence=75, reason="APY spike detected")
        assert r.action == "BUY"
        assert r.confidence == 75
        assert r.timestamp is not None

    def test_json_serialization(self) -> None:
        r = JudgmentRecord(action="HOLD", confidence=30, geo_risk_score=85)
        data = json.loads(r.model_dump_json())
        assert data["action"] == "HOLD"
        assert data["geo_risk_score"] == 85


class TestJudgmentLogger:
    @pytest.mark.asyncio
    async def test_initialize_creates_dir(self, judgment_logger, tmp_log_dir) -> None:
        await judgment_logger.initialize()
        assert Path(tmp_log_dir).exists()

    @pytest.mark.asyncio
    async def test_record_writes_jsonl(self, judgment_logger, tmp_log_dir) -> None:
        await judgment_logger.initialize()
        record = JudgmentRecord(action="BUY", confidence=80, reason="High APY")
        await judgment_logger.record(record)

        jsonl_path = Path(tmp_log_dir) / "judgment_log.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_cognitive_state_updates(self, judgment_logger) -> None:
        await judgment_logger.initialize()

        for action in ["HOLD", "HOLD", "HOLD", "BUY"]:
            await judgment_logger.record(JudgmentRecord(action=action, confidence=50))

        state = judgment_logger.get_cognitive_state()
        assert state.total_judgments == 4
        assert state.last_action == "BUY"
        assert state.consecutive_holds == 0  # Reset by BUY

    @pytest.mark.asyncio
    async def test_consecutive_holds_tracked(self, judgment_logger) -> None:
        await judgment_logger.initialize()

        for _ in range(5):
            await judgment_logger.record(JudgmentRecord(action="HOLD", confidence=30))

        state = judgment_logger.get_cognitive_state()
        assert state.consecutive_holds == 5

    @pytest.mark.asyncio
    async def test_prompt_context_generation(self, judgment_logger) -> None:
        await judgment_logger.initialize()
        await judgment_logger.record(
            JudgmentRecord(action="SELL", confidence=70, reason="HF dropping")
        )

        state = judgment_logger.get_cognitive_state()
        prompt = state.to_prompt_context()
        assert "SELL" in prompt
        assert "70%" in prompt

    @pytest.mark.asyncio
    async def test_consecutive_holds_warning_in_prompt(self, judgment_logger) -> None:
        await judgment_logger.initialize()
        for _ in range(4):
            await judgment_logger.record(JudgmentRecord(action="HOLD", confidence=30))

        prompt = judgment_logger.get_cognitive_state().to_prompt_context()
        assert "consecutive HOLDs" in prompt

    @pytest.mark.asyncio
    async def test_reload_from_jsonl(self, tmp_log_dir) -> None:
        """Crash recovery: reload state from JSONL file."""
        logger1 = JudgmentLogger(log_dir=tmp_log_dir)
        await logger1.initialize()
        await logger1.record(JudgmentRecord(action="BUY", confidence=80))
        await logger1.record(JudgmentRecord(action="HOLD", confidence=40))

        # Simulate restart with new instance
        logger2 = JudgmentLogger(log_dir=tmp_log_dir)
        await logger2.initialize()

        state = logger2.get_cognitive_state()
        assert state.total_judgments == 2
        assert state.last_action == "HOLD"

    @pytest.mark.asyncio
    async def test_recent_judgments(self, judgment_logger) -> None:
        await judgment_logger.initialize()
        for i in range(10):
            await judgment_logger.record(
                JudgmentRecord(
                    action="HOLD" if i % 2 == 0 else "BUY",
                    confidence=50 + i,
                )
            )

        recent = judgment_logger.get_recent_judgments(3)
        assert len(recent) == 3
        assert recent[-1].confidence == 59

    @pytest.mark.asyncio
    async def test_empty_state_prompt(self, judgment_logger) -> None:
        await judgment_logger.initialize()
        state = judgment_logger.get_cognitive_state()
        prompt = state.to_prompt_context()
        assert "No previous judgments" in prompt

    @pytest.mark.asyncio
    async def test_update_outcome_win_rate(self, judgment_logger) -> None:
        await judgment_logger.initialize()
        r = JudgmentRecord(action="BUY", confidence=80)
        await judgment_logger.record(r)
        await judgment_logger.update_outcome(r.timestamp, was_correct=True, apy_change="+2.1%")

        state = judgment_logger.get_cognitive_state()
        assert state.win_rate == 1.0


class TestCognitiveState:
    def test_empty_state(self) -> None:
        state = CognitiveState()
        assert state.total_judgments == 0
        assert state.consecutive_holds == 0
        assert "No previous judgments" in state.to_prompt_context()

    def test_win_rate_in_prompt(self) -> None:
        state = CognitiveState(
            total_judgments=10,
            last_action="BUY",
            last_confidence=75,
            win_rate=0.7,
        )
        prompt = state.to_prompt_context()
        assert "70%" in prompt
        assert "win rate" in prompt
