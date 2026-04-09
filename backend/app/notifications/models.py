# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/models.py
"""
通知ログ ORM モデル定義。

notification_logs テーブル: 送信された通知を永続化する。
partner_id が NULL の通知はシステム全体向けであり、パートナー画面には表示しない。

手動マイグレーション SQL（Alembicなし、staging DB に直接実行）:
    CREATE TABLE IF NOT EXISTS notification_logs (
        id         SERIAL PRIMARY KEY,
        channel    VARCHAR(50)  NOT NULL,
        severity   VARCHAR(20)  NOT NULL,
        title      VARCHAR(255) NOT NULL,
        body       TEXT         NOT NULL,
        partner_id INTEGER      REFERENCES users(id) ON DELETE SET NULL,
        user_id    INTEGER      REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_notification_logs_partner_id
        ON notification_logs (partner_id);
    CREATE INDEX IF NOT EXISTS ix_notification_logs_created_at
        ON notification_logs (created_at DESC);
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationLog(Base):
    """
    通知ログテーブル。

    Attributes:
        id: プライマリキー
        channel: 通知チャンネル (internal_log / line / slack / email)
        severity: 重要度 (info / warning / alert / emergency)
        title: 通知タイトル
        body: 通知本文
        partner_id: 対象パートナーの users.id (nullable: NULLはシステム全体向け)
        user_id: 対象ユーザーの users.id (nullable)
        created_at: 通知生成日時 (UTC)
    """

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    partner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, severity={self.severity!r}, "
            f"title={self.title!r}, partner_id={self.partner_id})>"
        )
