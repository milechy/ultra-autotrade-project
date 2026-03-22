# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/models.py
"""AI判定結果の永続化モデル。"""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIDecision(Base):
    """AI判定結果テーブル。"""

    __tablename__ = "ai_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    primary_action: Mapped[str] = mapped_column(String(10), nullable=False)
    primary_confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    secondary_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    secondary_action: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    secondary_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agreed: Mapped[bool] = mapped_column(Boolean, default=False)
    rag_context_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
