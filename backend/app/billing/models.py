# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/models.py
"""
Billing モジュールの SQLAlchemy モデル定義。

テーブル:
- fee_configs      : 手数料設定（管理報酬率・成果報酬率・HWM 有効化）
- fee_calculations : ユーザーごとの手数料計算履歴
- high_water_marks : ユーザーごとの HWM（High Water Mark）
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeeConfig(Base):
    """
    手数料設定テーブル。

    Attributes:
        id: プライマリキー
        management_fee_rate: 管理報酬率（年率、デフォルト 0.5%）
        performance_fee_rate: 成果報酬率（デフォルト 10%）
        high_water_mark_enabled: HWM を使用するか
        minimum_aum: 最低 AUM（この金額未満のユーザーはスキップ）
        created_at: 作成日時
        updated_at: 更新日時
    """

    __tablename__ = "fee_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    management_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6, asdecimal=True),
        nullable=False,
        default=Decimal("0.005"),
    )
    performance_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6, asdecimal=True),
        nullable=False,
        default=Decimal("0.10"),
    )
    high_water_mark_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    minimum_aum: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
        default=Decimal("3000"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<FeeConfig(id={self.id}, "
            f"mgmt={self.management_fee_rate}, "
            f"perf={self.performance_fee_rate})>"
        )


class FeeCalculation(Base):
    """
    手数料計算履歴テーブル。

    Attributes:
        id: プライマリキー
        user_id: ユーザー ID（users.id への外部キー）
        calculation_date: 計算日
        period_type: 期間種別（'daily' または 'monthly'）
        aum_snapshot: 計算時の AUM スナップショット
        management_fee: 管理報酬
        performance_fee: 成果報酬
        total_fee: 合計手数料
        profit_since_hwm: HWM 以降の利益
        high_water_mark: 計算時の HWM
        created_at: 作成日時
    """

    __tablename__ = "fee_calculations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    aum_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    management_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    performance_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    total_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    profit_since_hwm: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    high_water_mark: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<FeeCalculation(id={self.id}, "
            f"user_id={self.user_id}, "
            f"date={self.calculation_date}, "
            f"total={self.total_fee})>"
        )


class HighWaterMark(Base):
    """
    High Water Mark テーブル。

    ユーザーごとに 1 レコード（unique(user_id)）。

    Attributes:
        id: プライマリキー
        user_id: ユーザー ID（users.id への外部キー、ユニーク）
        hwm_value: HWM 値
        updated_at: 更新日時
    """

    __tablename__ = "high_water_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    hwm_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 6, asdecimal=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<HighWaterMark(user_id={self.user_id}, hwm={self.hwm_value})>"
