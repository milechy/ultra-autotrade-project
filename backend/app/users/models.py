# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/models.py
"""ユーザー設定モデル定義。"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSettings(Base):
    """
    ユーザー設定テーブル。

    ユーザーごとの通知設定・取引上限・リスクモード等を格納する。
    users テーブルとは 1:1 の関係。

    Attributes:
        id: プライマリキー
        user_id: ユーザー ID（users.id への外部キー、ユニーク）
        notification_email: 通知用メールアドレス
        notification_frequency: 通知頻度 (all / important / none)
        max_single_trade_usd: 単一取引の上限金額（USD）
        max_daily_trade_usd: 日次取引の上限金額（USD）
        risk_mode: リスクモード (conservative / balanced / aggressive)
        dark_mode: ダークモード有効化フラグ
        language: 言語設定 (ja / en)
        two_factor_enabled: 二段階認証有効化フラグ
        created_at: 作成日時
        updated_at: 更新日時
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    notification_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    notification_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="important"
    )
    max_single_trade_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True, default=None
    )
    max_daily_trade_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True, default=None
    )
    risk_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="conservative")
    dark_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ja")
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
        return f"<UserSettings(user_id={self.user_id}, risk_mode={self.risk_mode})>"
