# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/action_models.py
"""学習データ層 (Hermes 受け入れ前提) の SQLAlchemy モデル定義。

P0-6 (docs/50_phase2_ai_optimizer_design.md §9):
  Alembic migration `h8i9j0k1l2m3_add_user_actions_and_ai_decision_features.py`
  で作成される 2 表 (user_actions / ai_decision_features) を ORM 経由で参照
  できるようにするためのモデル定義。

  - UserAction:
      manual UI / onboarding 経由の click ログ (supervised signal)。
      `user_actions` テーブル。
  - AIDecisionFeatures:
      `ai_decisions` と 1:1 で、判定時点の特徴量 (market_apy_supply 等) を
      正規化保存する `ai_decision_features` テーブル。

  既存 SQLAlchemy `Base` (backend/app/database.py:20) を共有する。
  既存テーブル (users / ai_decisions / portfolio_snapshots) には touch しない:
  ForeignKey 文字列参照のみで relationship は遅延解決する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    # 循環参照防止のため runtime には import しない。relationship は文字列参照。
    from app.ai.models import AIDecision
    from app.auth.models import User
    from app.portfolio.models import PortfolioSnapshot


class UserAction(Base):
    """ユーザ行動ログ (`user_actions`)。

    manual UI / onboarding 経由のユーザ click を supervised signal として
    蓄積する。`session_id` 一致もしくは `clicked_at` 近接時刻で
    `ai_decisions` と結合する。

    Attributes:
        id: プライマリキー
        user_id: ユーザ ID (users.id への FK)
        action_type: 行動種別 (e.g. ``manual_buy_click`` / ``manual_sell_click``
            / ``onramp_completed``)
        target_type: 対象種別 (e.g. ``proposal`` / ``asset``)
        target_id: 対象 ID (proposal_id / 資産シンボル等の任意文字列)
        clicked_at: クリック時刻 (TZ 付き)
        session_id: セッション識別子 (UI 側で発行)
        context_json: 任意 context (JSONB)。PII を含めない運用ルール。
    """

    __tablename__ = "user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    # PostgreSQL では JSONB、SQLite では JSON にフォールバックする。
    # 既存 models.py 群が generic JSON を多用しているのに合わせる。
    context_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(
        "User",
        primaryjoin="UserAction.user_id == User.id",
        foreign_keys=[user_id],
        lazy="select",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<UserAction(id={self.id}, user_id={self.user_id}, "
            f"action_type={self.action_type!r}, clicked_at={self.clicked_at})>"
        )


class AIDecisionFeatures(Base):
    """AI 判定特徴量 (`ai_decision_features`)。

    `ai_decisions` と 1:1 (UNIQUE) で、判定時点のマーケット/ポートフォリオ
    特徴量を正規化保存する。`ai_decisions.rag_context_json` は監査・人間
    読解用に維持し、高頻度な学習クエリは本表で行う。

    Attributes:
        id: プライマリキー
        ai_decision_id: `ai_decisions.id` への FK (UNIQUE)
        portfolio_snapshot_id: `portfolio_snapshots.id` への FK (nullable)
        market_apy_supply / market_apy_borrow: 判定時点の APY (%)
        health_factor: 判定時点の HF
        gas_gwei: 判定時点の Gas (gwei)
        price_usd: 判定時点の主要資産価格 (USD)
        prompt_features_json: 任意の追加特徴量 (PII フィルタ済み JSON)
        created_at: 作成日時
    """

    __tablename__ = "ai_decision_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ai_decision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_decisions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    portfolio_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("portfolio_snapshots.id"),
        nullable=True,
        index=True,
    )
    market_apy_supply: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    market_apy_borrow: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    health_factor: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    gas_gwei: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=4), nullable=True
    )
    price_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=8), nullable=True
    )
    prompt_features_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    decision: Mapped["AIDecision"] = relationship(
        "AIDecision",
        primaryjoin="AIDecisionFeatures.ai_decision_id == AIDecision.id",
        foreign_keys=[ai_decision_id],
        lazy="select",
        viewonly=True,
    )
    snapshot: Mapped[Optional["PortfolioSnapshot"]] = relationship(
        "PortfolioSnapshot",
        primaryjoin="AIDecisionFeatures.portfolio_snapshot_id == PortfolioSnapshot.id",
        foreign_keys=[portfolio_snapshot_id],
        lazy="select",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AIDecisionFeatures(id={self.id}, "
            f"ai_decision_id={self.ai_decision_id}, "
            f"portfolio_snapshot_id={self.portfolio_snapshot_id})>"
        )
