# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/models.py
"""AI判定結果の永続化モデル。"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _embedding_column_type() -> Any:
    """pgvector が利用可能な場合は Vector(1536)、否の場合は Text を返す。"""
    try:
        from pgvector.sqlalchemy import Vector  # noqa: PLC0415

        return Vector(1536)
    except ImportError:
        return Text()


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
    # ALTER TABLE ai_decisions ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(10) DEFAULT 'v1';
    prompt_version: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class AiDecisionFeature(Base):
    """AI判定時の特徴量テーブル (Hermes Phase 0 capture)。

    ai_decisions と 1:1。判定ループから INSERT される。
    列選定: fetch_aave_market_data_safe() + run_all_agents() で取得できる値のみ。
    RSI/MACD/volatility/gas 等、現コードに存在しない値は含めない (NULL確定列禁止)。
    """

    __tablename__ = "ai_decision_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ai_decision_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, unique=True)
    # 4エージェント (indicator/pattern/risk/macro) の bias+confidence+key_data
    agent_signals: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Aave raw (utilization/supply_apy/borrow_apy/health_factor) + geo/macro コンテキスト
    raw_features: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    judge_action: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    cross_verify: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # text-embedding-3-small 1536次元。pgvector 利用可能時のみ実値が入る。NULL許容 (fail-open)。
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        _embedding_column_type(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AiDecisionOutcome(Base):
    """AI判定の実績アウトカムテーブル。

    行の種類:
      1. partner_approved 行 (horizon_hours=NULL): 承認/却下エンドポイントから即時 INSERT
      2. horizon=24h / 48h 行: outcome_labeling_batch が後付けで INSERT

    asset / protocol は将来の複数資産・プロトコル対応のために最初から持つ。
    既存行は migration で 'USDC' / 'aave_v3' にバックフィル済み。
    """

    __tablename__ = "ai_decision_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    horizon_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    realized_yield_delta: Mapped[Optional[Any]] = mapped_column(
        Numeric(precision=20, scale=8), nullable=True
    )
    gas_cost_usd: Mapped[Optional[Any]] = mapped_column(
        Numeric(precision=20, scale=8), nullable=True
    )
    hf_min_after: Mapped[Optional[Any]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    partner_approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    regret_score: Mapped[Optional[Any]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    is_positive_example: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    asset: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default="USDC", server_default="USDC"
    )
    protocol: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="aave_v3", server_default="aave_v3"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class UserAction(Base):
    """ユーザ行動ログ (supervised signal)。

    manual UI / onboarding 経由でのクリックを蓄積し、後段の学習データ抽出で
    ai_decisions と結合して判定→行動の系列を学習データ化する。
    """

    __tablename__ = "user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    context_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
