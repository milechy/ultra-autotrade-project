"""
AI Judgment Log — Event Log + Cognitive State pattern.

Two responsibilities:
1. Event Log (JSONL): Append-only audit trail of every AI judgment.
   Survives crashes, queryable with jq, immutable once written.

2. Cognitive State: Remembers recent judgments to provide context
   for future decisions ("last time we saw similar conditions, we chose X
   and the market moved Y").

Design principles:
  - JSONL for crash recovery — every judgment persisted before execution
  - Cognitive state feeds back into LLM prompt for self-improving judgment
  - File + memory dual storage (JSONL is source of truth, memory is cache)
"""

import asyncio
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

JUDGMENT_LOG_DIR = os.getenv("JUDGMENT_LOG_DIR", "/var/log/ultra-autotrade")
JUDGMENT_LOG_FILE = "judgment_log.jsonl"
MAX_RECENT = 20


# ============================================================
# Schemas
# ============================================================
class JudgmentRecord(BaseModel):
    """Single AI judgment record — one line in JSONL."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = Field(..., description="BUY / SELL / HOLD")
    confidence: int = Field(..., ge=0, le=100)
    reason: Optional[str] = None

    # Cross-validation
    primary_action: Optional[str] = None
    secondary_action: Optional[str] = None
    agreed: Optional[bool] = None

    # Market context at judgment time
    health_factor: Optional[str] = None
    geo_risk_score: Optional[int] = None
    news_sentiment: Optional[str] = None
    fed_stance: Optional[str] = None

    # Outcome (filled later by review)
    outcome_apy_change: Optional[str] = None
    outcome_hf_change: Optional[str] = None
    outcome_was_correct: Optional[bool] = None


class CognitiveState(BaseModel):
    """AI's short-term memory of recent judgments.

    Fed into LLM prompt as "recent decision history" to avoid
    flip-flopping and enable self-reflection.
    """

    recent_actions: list[str] = Field(default_factory=list, description="Last 5 actions")
    recent_confidences: list[int] = Field(
        default_factory=list, description="Last 5 confidence scores"
    )
    last_action: Optional[str] = None
    last_confidence: Optional[int] = None
    last_reason: Optional[str] = None
    last_timestamp: Optional[datetime] = None
    consecutive_holds: int = 0
    total_judgments: int = 0
    win_rate: Optional[float] = None

    def to_prompt_context(self) -> str:
        """Format cognitive state for LLM prompt injection."""
        if self.total_judgments == 0:
            return "[Decision History] No previous judgments recorded."

        parts = [
            f"[Decision History] Total judgments: {self.total_judgments}",
            f"  Last action: {self.last_action} (confidence: {self.last_confidence}%)",
        ]
        if self.last_reason:
            parts.append(f"  Last reason: {self.last_reason[:100]}")
        if self.consecutive_holds > 2:
            parts.append(
                f"  Warning: {self.consecutive_holds} consecutive HOLDs"
                " — consider if conditions have changed"
            )
        if self.win_rate is not None:
            parts.append(f"  Historical win rate: {self.win_rate:.0%}")
        if self.recent_actions:
            parts.append(f"  Recent pattern: {' -> '.join(self.recent_actions[-5:])}")
        return "\n".join(parts)


# ============================================================
# Judgment Logger (JSONL + Cognitive State)
# ============================================================
class JudgmentLogger:
    """Append-only JSONL logger + in-memory cognitive state."""

    def __init__(self, log_dir: Optional[str] = None) -> None:
        self._log_dir = Path(log_dir or JUDGMENT_LOG_DIR)
        self._log_path = self._log_dir / JUDGMENT_LOG_FILE
        self._recent: deque[JudgmentRecord] = deque(maxlen=MAX_RECENT)
        self._cognitive = CognitiveState()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Create log directory and load recent state from existing JSONL."""
        if self._initialized:
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            if self._log_path.exists():
                with open(self._log_path) as f:
                    lines = f.readlines()
                for line in lines[-MAX_RECENT:]:
                    try:
                        record = JudgmentRecord.model_validate_json(line.strip())
                        self._recent.append(record)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Skipping malformed JSONL line: %s", exc)
                        continue
                self._rebuild_cognitive_state()
            self._initialized = True
            logger.info(
                "JudgmentLogger initialized: %s (%d recent records)",
                self._log_path,
                len(self._recent),
            )
        except Exception as exc:
            logger.error("JudgmentLogger initialization failed: %s", exc)
            self._initialized = True  # Don't retry, just log

    async def record(self, record: JudgmentRecord) -> None:
        """Append a judgment record to JSONL and update cognitive state."""
        async with self._lock:
            try:
                with open(self._log_path, "a") as f:
                    f.write(record.model_dump_json() + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as exc:
                logger.error("Failed to write judgment log: %s", exc)

            self._recent.append(record)
            self._update_cognitive(record)

    def _update_cognitive(self, record: JudgmentRecord) -> None:
        """Update cognitive state from a new record."""
        self._cognitive.last_action = record.action
        self._cognitive.last_confidence = record.confidence
        self._cognitive.last_reason = record.reason
        self._cognitive.last_timestamp = record.timestamp
        self._cognitive.total_judgments += 1

        self._cognitive.recent_actions.append(record.action)
        if len(self._cognitive.recent_actions) > 5:
            self._cognitive.recent_actions = self._cognitive.recent_actions[-5:]

        self._cognitive.recent_confidences.append(record.confidence)
        if len(self._cognitive.recent_confidences) > 5:
            self._cognitive.recent_confidences = self._cognitive.recent_confidences[-5:]

        if record.action == "HOLD":
            self._cognitive.consecutive_holds += 1
        else:
            self._cognitive.consecutive_holds = 0

    def _rebuild_cognitive_state(self) -> None:
        """Rebuild cognitive state from recent records (after loading from JSONL)."""
        self._cognitive = CognitiveState()
        for record in self._recent:
            self._update_cognitive(record)

    def get_cognitive_state(self) -> CognitiveState:
        """Get current cognitive state for prompt injection."""
        return self._cognitive

    def get_recent_judgments(self, count: int = 5) -> list[JudgmentRecord]:
        """Get the most recent N judgments."""
        return list(self._recent)[-count:]

    def record_nowait(self, record: JudgmentRecord) -> None:
        """Sync record for use in non-async contexts. No lock (caller ensures single-writer)."""
        try:
            with open(self._log_path, "a") as f:
                f.write(record.model_dump_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as exc:
            logger.error("Failed to write judgment log: %s", exc)
        self._recent.append(record)
        self._update_cognitive(record)

    async def update_outcome(
        self,
        timestamp: datetime,
        was_correct: bool,
        apy_change: Optional[str] = None,
        hf_change: Optional[str] = None,
    ) -> None:
        """Update a past judgment with its outcome (called by review process)."""
        async with self._lock:
            for record in self._recent:
                if record.timestamp == timestamp:
                    record.outcome_was_correct = was_correct
                    record.outcome_apy_change = apy_change
                    record.outcome_hf_change = hf_change
                    break
            outcomes = [
                r.outcome_was_correct for r in self._recent if r.outcome_was_correct is not None
            ]
            if outcomes:
                self._cognitive.win_rate = sum(outcomes) / len(outcomes)


# ============================================================
# Global singleton
# ============================================================
_logger_instance: Optional[JudgmentLogger] = None


def get_judgment_logger() -> JudgmentLogger:
    """Get or create the global JudgmentLogger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = JudgmentLogger()
    return _logger_instance
