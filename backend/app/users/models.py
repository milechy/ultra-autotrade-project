# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/models.py
"""ユーザー設定モデル定義。

本モジュールは main.py から `from app.users.models import UserSettings  # noqa: F401`
でインポートされ、Base.metadata.create_all() 時にテーブルが自動作成される。
Alembic 不使用プロジェクトのため、下記 SQL は手動実行が必要なバックアップとして保持する。

手動 CREATE TABLE SQL (新規環境・DB 再構築時):
    CREATE TABLE IF NOT EXISTS user_settings (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        notification_email      VARCHAR(255),
        notification_frequency  VARCHAR(20)  NOT NULL DEFAULT 'important',
        max_single_trade_usd    NUMERIC(20,2),
        max_daily_trade_usd     NUMERIC(20,2),
        risk_mode       VARCHAR(20)  NOT NULL DEFAULT 'conservative',
        dark_mode       BOOLEAN      NOT NULL DEFAULT TRUE,
        language        VARCHAR(10)  NOT NULL DEFAULT 'ja',
        two_factor_enabled BOOLEAN  NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings (user_id);
"""

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


# アカウント削除申請の status 値（models.py を唯一の真実源とする / CHECK は migration 内で独自定義しない）
ACCOUNT_DELETION_STATUS_PENDING = "pending"
ACCOUNT_DELETION_STATUS_PROCESSED = "processed"
ACCOUNT_DELETION_STATUS_CANCELLED = "cancelled"


class AccountDeletionRequest(Base):
    """アカウント削除申請テーブル。

    ユーザーからの削除申請を耐久的に記録する（APPI / 個人情報保護法対応）。
    本モジュールは main.py から import され、Base.metadata.create_all() 時に
    テーブルが自動作成される。status は application-layer で制御する
    （'pending' / 'processed' / 'cancelled'）。CHECK 制約を migration 内で
    独自定義しない（models.py が唯一の真実源）。

    手動 CREATE TABLE SQL (新規環境・DB 再構築時):
        CREATE TABLE IF NOT EXISTS account_deletion_requests (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status       VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_account_deletion_requests_user_id
            ON account_deletion_requests (user_id);
    """

    __tablename__ = "account_deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ACCOUNT_DELETION_STATUS_PENDING
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<AccountDeletionRequest(user_id={self.user_id}, status={self.status})>"
