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

---

push_subscriptions テーブル (2026-08-05, Alembic z7a8b9c0d1e2):
Web Push 購読を保持する。

以前は ``users.notification_settings_json`` (TEXT) の ``push_subscriptions`` キーに
JSON 配列として保存していたが、同じセルに通知設定 (push_enabled / preferences) が
同居しており、双方が read-modify-write で別セッションから書くため lost update が
発生していた (購読 1 件、または設定変更 1 回が黙って消える)。
専用テーブルへ分離することで read-modify-write そのものが無くなり、
endpoint のグローバル一意性も UNIQUE 制約が保証する
(旧実装は全ユーザー走査でこれを模倣していた)。

手動マイグレーション SQL (alembic を使わない環境向けの参考):
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id         SERIAL       PRIMARY KEY,
        endpoint   TEXT         NOT NULL UNIQUE,
        user_id    INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        p256dh     VARCHAR(255) NOT NULL,
        auth       VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id
        ON push_subscriptions (user_id);
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


class PushSubscription(Base):
    """
    Web Push 購読テーブル (2026-08-05)。

    Base.metadata への登録経路: main.py → notifications.router → .push →
    ``from .models import PushSubscription``。push.py が実際に本モデルを使うため
    連鎖 import で必ず読み込まれる。NotificationLog のような main.py での明示 import
    (noqa: F401) は不要 (main.py は凍結ファイルであり、不要な変更を避ける)。

    Attributes:
        id: プライマリキー
        endpoint: ブラウザの push service endpoint URL (グローバルに一意)
        user_id: 購読者の users.id (ユーザー削除で CASCADE 削除)
        p256dh: 購読の公開鍵 (ブラウザ PushSubscription.keys.p256dh)
        auth: 購読の認証シークレット (同 keys.auth)
        created_at: 登録日時 (UTC)
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # endpoint はブラウザ (オリジン) 単位でグローバルに一意。UNIQUE 制約が
    # 「同一端末が同時に 2 ユーザーへ属さない」を DB レベルで保証する。
    # これが無いと、同一端末で別アカウントにログインした後も旧ユーザー宛の
    # 通知 (金額・資産情報) が同じ端末に届き続ける (I-12)。
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<PushSubscription(id={self.id}, user_id={self.user_id}, "
            f"endpoint={self.endpoint[:30]!r})>"
        )
