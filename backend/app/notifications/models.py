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
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        delivered  BOOLEAN      NULL
    );
    CREATE INDEX IF NOT EXISTS ix_notification_logs_partner_id
        ON notification_logs (partner_id);
    CREATE INDEX IF NOT EXISTS ix_notification_logs_created_at
        ON notification_logs (created_at DESC);

delivered 列 (2026-08-04 PR3, Alembic x4y5z6a7b8c9 の次): NULL=対象外/未計測、
True=配信先に到達確認済み、False=配信失敗(410等)。行の存在自体が「送信した」を表し、
この列が「到達した」を表す。実際の書き込み配線は PR5 で行う (本PRはスキーマ追加のみ)。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
        delivered: 配信先への到達確認 (nullable: NULL=対象外/未計測、実書き込みはPR5)
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
    delivered: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, severity={self.severity!r}, "
            f"title={self.title!r}, partner_id={self.partner_id})>"
        )
