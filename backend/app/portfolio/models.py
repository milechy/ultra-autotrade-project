# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/models.py
"""ポートフォリオスナップショットモデル定義。"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import JSON, DateTime, Integer, Numeric
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
