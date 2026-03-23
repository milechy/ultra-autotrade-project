# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/models.py
"""ポートフォリオスナップショットモデル定義。"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import JSON, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioSnapshot(Base):
    """ポートフォリオスナップショットテーブル。"""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_value_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    total_supply_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=2), nullable=False
    )
    total_borrow_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=2), nullable=False
    )
    health_factor: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    positions_json: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class PortfolioHistory(Base):
    """
    ポートフォリオ履歴テーブル。

    日次・週次・月次のポートフォリオ集計値を時系列で記録する。
    スナップショットより粒度を粗く保持し、グラフ表示等に活用する。

    Attributes:
        id: プライマリキー
        user_id: ユーザー ID
        period_type: 集計期間種別 (daily / weekly / monthly)
        period_start: 集計期間の開始日時
        period_end: 集計期間の終了日時
        open_value_usd: 期間開始時のポートフォリオ評価額 (USD)
        close_value_usd: 期間終了時のポートフォリオ評価額 (USD)
        high_value_usd: 期間内の最高評価額 (USD)
        low_value_usd: 期間内の最低評価額 (USD)
        pnl_usd: 期間内の損益 (USD)
        pnl_pct: 期間内の損益率 (%)
        avg_health_factor: 期間内の平均ヘルスファクター
        snapshot_count: 集計元スナップショット数
        created_at: 作成日時
    """

    __tablename__ = "portfolio_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_value_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    close_value_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=2), nullable=False
    )
    high_value_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    low_value_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    pnl_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    pnl_pct: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    avg_health_factor: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioHistory(user_id={self.user_id}, "
            f"period={self.period_type}, "
            f"start={self.period_start})>"
        )
