# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/models.py
"""
ユーザーモデル定義。

docs/13_security_design.md に準拠したセキュリティ要件を満たす。

ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'LOWER';
ALTER TABLE users ADD COLUMN last_judgment_at TIMESTAMP WITH TIME ZONE NULL;
-- 注: F-2 で DEFAULT を 'GENERAL' から 'LOWER' に変更。本番 DB の DEFAULT 切替は
-- F-16 マイグレーションで実施 (docs/46_users_tier_migration_plan.md 参照)。
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, Enum):
    """ユーザーロール。"""

    ADMIN = "admin"
    PARTNER = "partner"
    EDITOR = "editor"
    VIEWER = "viewer"


class InvestmentTier(str, Enum):
    """投資ティア。

    v10 (F-2 2026-04-25 〜): LOWER / MIDDLE / UPPER の 3 層
      - LOWER:  〜1,000,000 円
      - MIDDLE: 1,000,001 〜 10,000,000 円
      - UPPER:  10,000,001 円 〜

    GENERAL は v9 過渡期互換値 (DEPRECATED)。F-16 で users.tier の
    全 GENERAL レコードを LOWER/MIDDLE/UPPER に再判定後、F-13 で本 enum から削除。
    """

    LOWER = "LOWER"
    MIDDLE = "MIDDLE"
    UPPER = "UPPER"
    GENERAL = "GENERAL"  # DEPRECATED (v9). 削除は F-13 (F-16 マイグレーション完了後)


#: v9 GENERAL → v10 デフォルト変換マップ (read-time fallback)。
#: F-16 マイグレーションで DB から GENERAL が消失した時点で参照箇所も削除可能。
LEGACY_TIER_MAP: dict[str, "InvestmentTier"] = {
    "GENERAL": InvestmentTier.LOWER,
}

#: tier 値 → 日本語ラベル。フロント表示および通知文言で使用。
TIER_JP_LABELS: dict[InvestmentTier, str] = {
    InvestmentTier.LOWER: "一般",
    InvestmentTier.MIDDLE: "ミドル",
    InvestmentTier.UPPER: "アッパー",
    InvestmentTier.GENERAL: "一般",  # GENERAL は LOWER と同じラベル (過渡期)
}


#: v10 tier 判定の境界値 (JPY)。
TIER_BOUNDARY_LOWER_JPY = 1_000_000  # LOWER / MIDDLE 境界
TIER_BOUNDARY_UPPER_JPY = 10_000_000  # MIDDLE / UPPER 境界


class User(Base):
    """
    ユーザーテーブル。

    Attributes:
        id: プライマリキー
        email: メールアドレス（ユニーク）
        username: ユーザー名（ユニーク）
        hashed_password: bcrypt ハッシュ化されたパスワード
        role: ユーザーロール（admin / viewer）
        is_active: アクティブ状態
        created_at: 作成日時
        updated_at: 更新日時
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.VIEWER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    terms_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)
    risk_mode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="conservative"
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
    user_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="managed")
    execution_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto_execute"
    )
    wallet_address: Mapped[Optional[str]] = mapped_column(
        String(42), unique=True, nullable=True, index=True, default=None
    )
    invited_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, default=None
    )
    tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvestmentTier.LOWER.value
    )
    last_judgment_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"

    @property
    def is_admin(self) -> bool:
        """管理者かどうか。"""
        return self.role == UserRole.ADMIN.value
