# backend/app/notifications/schemas.py

"""
通知メッセージの共通スキーマ定義。

Phase5 時点では:
- 通知のチャンネル種別（どこに送るか）
- 通知の重要度
- タイトル＋本文

のみを扱い、実際の送信先（LINE/Slackなど）の具体的な情報は
後続フェーズで Sender 実装側に持たせる前提とする。

※ セキュリティ上の観点から、NotificationMessage 自体には
  API キーやウォレットアドレスなどの機密情報は含めないこと。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NotificationChannel(str, Enum):
    """
    通知の論理的なチャンネル種別。

    - INTERNAL_LOG: アプリ内部ログ（Phase5 デフォルト）
    - LINE: 将来の LINE 通知
    - SLACK: 将来の Slack 通知
    - EMAIL: 将来の Email 通知
    """

    INTERNAL_LOG = "internal_log"
    LINE = "line"
    SLACK = "slack"
    EMAIL = "email"


class NotificationSeverity(str, Enum):
    """
    通知の重要度。

    監視イベントの AlertLevel と概ね対応するが、
    通知側はもう少し粗い粒度で扱う。
    """

    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    EMERGENCY = "emergency"


class NotificationMessage(BaseModel):
    """
    通知 1件分の情報。

    body はプレーンテキスト想定。
    機密情報は含めないこと（docs/13_security_design.md）。
    """

    channel: NotificationChannel = Field(
        ...,
        description="論理的な通知チャンネル（LINE/Slack などは Sender 実装側で解釈）。",
    )
    severity: NotificationSeverity = Field(
        ...,
        description="通知の重要度。",
    )
    title: str = Field(
        ...,
        description="短いタイトル（チャットの1行目など）。",
    )
    body: str = Field(
        ...,
        description="本文。プレーンテキスト想定。",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="通知生成時刻（UTC）。",
    )

    class Config:
        # ログ用途で使うため、repr を簡潔にしておく
        orm_mode = True
