# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/feedback_models.py
"""AI判定フィードバックモデル定義 (Layer 4)。

AIFeedback テーブルをフィードバック記録の「正本」とする。
JudgmentLogger の JSONL outcome_was_correct は参考用（二重管理を避ける）。

DB マイグレーション（Alembic未使用 — 手動 ALTER）:
  CREATE TABLE ai_feedbacks (
      id SERIAL PRIMARY KEY,
      ai_decision_id INTEGER NOT NULL,
      is_correct BOOLEAN,
      actual_outcome VARCHAR(20) NOT NULL,
      pnl_usd NUMERIC(20, 6),
      expected_apy NUMERIC(10, 4),
      actual_apy NUMERIC(10, 4),
      improvement_suggestion TEXT,
      feedback_source VARCHAR(20) NOT NULL DEFAULT 'manual',
      recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
      recorded_by VARCHAR(100),
      created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
  );
  CREATE INDEX idx_ai_feedbacks_decision_id ON ai_feedbacks(ai_decision_id);
  CREATE INDEX idx_ai_feedbacks_recorded_at ON ai_feedbacks(recorded_at);
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ---------------------------------------------------------------------------
# actual_outcome の有効値
# ---------------------------------------------------------------------------
ACTUAL_OUTCOME_VALUES = ("profit", "loss", "neutral", "unknown")
FEEDBACK_SOURCE_VALUES = ("manual", "auto_howl", "auto_outcome")


# ============================================================
# SQLAlchemy モデル
# ============================================================
class AIFeedback(Base):
    """AI判定フィードバックテーブル。

    ai_decision_id は ai_decisions.id を参照するが、
    SQLite テスト互換のため SQLAlchemy レベルの ForeignKey 制約は設けない。
    参照整合性は PostgreSQL 本番側の DDL で担保する。
    """

    __tablename__ = "ai_feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ai_decision_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # "profit" | "loss" | "neutral" | "unknown"
    actual_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    pnl_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    expected_apy: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    actual_apy: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    improvement_suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "manual" | "auto_howl" | "auto_outcome"
    feedback_source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    recorded_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ============================================================
# Pydantic スキーマ
# ============================================================
class AIFeedbackCreate(BaseModel):
    """フィードバック記録リクエスト。"""

    ai_decision_id: int
    is_correct: Optional[bool] = None
    actual_outcome: Literal["profit", "loss", "neutral", "unknown"]
    pnl_usd: Optional[Decimal] = None
    expected_apy: Optional[Decimal] = None
    actual_apy: Optional[Decimal] = None
    improvement_suggestion: Optional[str] = None

    @field_validator("improvement_suggestion")
    @classmethod
    def truncate_suggestion(cls, v: Optional[str]) -> Optional[str]:
        """改善提案は 2000 文字に制限する。"""
        if v is not None and len(v) > 2000:
            return v[:2000]
        return v


class AIFeedbackResponse(BaseModel):
    """フィードバック応答スキーマ。Decimal は文字列で返す（JSON シリアライズ）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ai_decision_id: int
    is_correct: Optional[bool]
    actual_outcome: str
    pnl_usd: Optional[str] = None
    expected_apy: Optional[str] = None
    actual_apy: Optional[str] = None
    improvement_suggestion: Optional[str]
    feedback_source: str
    recorded_at: datetime
    recorded_by: Optional[str]
    created_at: datetime

    @field_validator("pnl_usd", "expected_apy", "actual_apy", mode="before")
    @classmethod
    def decimal_to_str(cls, v: object) -> Optional[str]:
        """Decimal → 文字列変換。"""
        if v is None:
            return None
        return str(v)


class AIFeedbackStats(BaseModel):
    """フィードバック統計応答。"""

    total_feedbacks: int
    correct_count: int
    incorrect_count: int
    accuracy_rate: Optional[float]  # correct / (correct + incorrect); None if no decided feedback
    avg_pnl_usd: Optional[str]  # Decimal as string; None if no pnl data
    feedback_by_source: dict[str, int]
