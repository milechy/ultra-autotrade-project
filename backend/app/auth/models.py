# backend/app/auth/models.py
"""
ユーザーモデル定義。

docs/13_security_design.md に準拠したセキュリティ要件を満たす。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, Enum):
    """ユーザーロール。"""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"

    @property
    def is_admin(self) -> bool:
        """管理者かどうか。"""
        return self.role == UserRole.ADMIN.value
