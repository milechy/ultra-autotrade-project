"""add push_subscriptions table

Web Push 購読を users.notification_settings_json (TEXT) の push_subscriptions キーから
専用テーブルへ移す。

背景: 同一セルに通知設定 (push_enabled / preferences) と購読配列が同居しており、
双方が read-modify-write で別セッションから書くため lost update が発生していた
(購読 1 件、または設定変更 1 回が黙って消える)。専用テーブルにすると
read-modify-write が無くなり問題クラス自体が消える。endpoint のグローバル一意性も
UNIQUE 制約が保証する (旧実装は全ユーザー走査で模倣していた)。

移行方針:
- 既存 JSON の push_subscriptions を新テーブルへ backfill する。本番は VAPID 未設定で
  購読が 0 件の想定だが、staging / dev に残っている可能性があるため実装する。
- **JSON 側の push_subscriptions キーは削除しない**。downgrade でデータを失わないため。
  アプリは以降このキーを読まないので実質無害。確認後の掃除は別タスク。

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-08-05

"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import context, op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "z7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "y6z7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_push_subscriptions_endpoint", "push_subscriptions", ["endpoint"], unique=True
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    _backfill_from_notification_settings_json()


def _backfill_from_notification_settings_json() -> None:
    """既存 JSON 内の購読を新テーブルへ移す。壊れた JSON / 要素はスキップする。

    offline モード (``alembic upgrade --sql``、レビュー用の SQL 生成) では
    SELECT の結果を取得できない (execute が None を返す) ためスキップする。
    その場合は下記 WARNING の指示どおり online で流すか、購読 0 件を確認して進める。
    """
    if context.is_offline_mode():
        logger.warning(
            "push_subscriptions backfill: offline モード (--sql) のためスキップしました。"
            "既存購読を移行するには online で `alembic upgrade head` を実行してください。"
        )
        return

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, notification_settings_json FROM users "
            "WHERE notification_settings_json IS NOT NULL"
        )
    ).fetchall()

    insert_sql = sa.text(
        "INSERT INTO push_subscriptions (endpoint, user_id, p256dh, auth) "
        "VALUES (:endpoint, :user_id, :p256dh, :auth)"
    )

    seen_endpoints: set[str] = set()
    migrated = 0
    for user_id, raw_json in rows:
        try:
            raw = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(raw, dict):
            continue
        subs = raw.get("push_subscriptions")
        if not isinstance(subs, list):
            continue
        for entry in subs:
            if not isinstance(entry, dict):
                continue
            endpoint = entry.get("endpoint")
            p256dh = entry.get("p256dh")
            auth = entry.get("auth")
            if not endpoint or not p256dh or not auth:
                continue
            # endpoint は UNIQUE。旧 JSON 実装のバグ等で重複していても落ちないようにする
            # (先に見つかった 1 件を採用)。
            if endpoint in seen_endpoints:
                continue
            seen_endpoints.add(endpoint)
            conn.execute(
                insert_sql,
                {"endpoint": endpoint, "user_id": user_id, "p256dh": p256dh, "auth": auth},
            )
            migrated += 1

    logger.info("push_subscriptions backfill: %d 件を移行しました。", migrated)


def downgrade() -> None:
    # JSON 側に元データが残っているため、テーブル削除で情報は失われない。
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_endpoint", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
