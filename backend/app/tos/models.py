# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/tos/models.py
"""
ToS 同意ログ ORM モデル定義 (MVP-P0-14 / GID 1215082217739006)。

tos_consents: ユーザーの利用規約同意を改ざん検知可能な形で永続化する。
tos_user_actions: ToS 同意の付随アクションログ (法的監査証跡)。
              Hermes 学習用の汎用 user_actions (app/ai/models.py, MVP-P0-6) とは
              別テーブル。法的監査証跡と学習特徴量は混在させない。

手動マイグレーション SQL (Alembic 未使用 / 本番 DB に直接実行):

    CREATE TABLE IF NOT EXISTS tos_consents (
        id            SERIAL PRIMARY KEY,
        user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        tos_version   VARCHAR(32)  NOT NULL,
        consent_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        ip            VARCHAR(64)  NULL,
        user_agent    VARCHAR(512) NULL,
        consent_hash  VARCHAR(64)  NOT NULL,
        is_demo_ack   BOOLEAN      NOT NULL DEFAULT FALSE
    );
    CREATE INDEX IF NOT EXISTS ix_tos_consents_user_id
        ON tos_consents (user_id);
    CREATE INDEX IF NOT EXISTS ix_tos_consents_consent_at
        ON tos_consents (consent_at DESC);

    CREATE TABLE IF NOT EXISTS tos_user_actions (
        id          SERIAL PRIMARY KEY,
        user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        action_type VARCHAR(64)  NOT NULL,
        payload     TEXT         NULL,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_tos_user_actions_user_id
        ON tos_user_actions (user_id);
    CREATE INDEX IF NOT EXISTS ix_tos_user_actions_action_type
        ON tos_user_actions (action_type);
    CREATE INDEX IF NOT EXISTS ix_tos_user_actions_created_at
        ON tos_user_actions (created_at DESC);
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ToSConsent(Base):
    """ToS 同意ログテーブル (改ざん検知用 hash 付き)。"""

    __tablename__ = "tos_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tos_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    consent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_demo_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ToSUserAction(Base):
    """ToS 同意の付随アクションログ (法的監査証跡)。

    NOTE: Hermes 学習用の汎用 user_actions テーブル (app/ai/models.py UserAction,
    MVP-P0-6) とは別テーブル `tos_user_actions`。法的監査証跡と学習特徴量は混在させない。
    """

    __tablename__ = "tos_user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
