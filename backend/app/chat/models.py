# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/chat/models.py
"""チャットメッセージモデル定義。

本モジュールは main.py から `from app.chat.models import ChatMessage  # noqa: F401`
でインポートされ、Base.metadata.create_all() 時にテーブルが自動作成される。
Alembic 不使用プロジェクトのため、下記 SQL は手動実行が必要なバックアップとして保持する。

手動 CREATE TABLE SQL (新規環境・DB 再構築時):
    CREATE TABLE IF NOT EXISTS chat_messages (
        id          BIGSERIAL PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role        VARCHAR(10) NOT NULL CHECK (role IN ('user', 'ai')),
        content     TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
        ON chat_messages (user_id, created_at DESC);
"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# SQLite でテストできるよう BigInteger を Integer にフォールバックする
_BIGINT_OR_INT = BigInteger().with_variant(Integer(), "sqlite")


class ChatMessage(Base):
    """
    チャットメッセージテーブル。

    ユーザーと AI の会話を時系列で格納する。
    users テーブルとは N:1 の関係。

    Attributes:
        id: プライマリキー（BigInteger）
        user_id: ユーザー ID（users.id への外部キー）
        role: メッセージ種別 ('user' または 'ai')
        content: メッセージ本文
        created_at: 作成日時（タイムゾーン付き）

    CHECK制約:
        role IN ('user', 'ai') — models.py を唯一の真実源とする。
        migration/SQL コメントと必ず一致させること。
    """

    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'ai')", name="ck_chat_messages_role"),)

    id: Mapped[int] = mapped_column(_BIGINT_OR_INT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
