# backend/app/notifications/config.py

"""
通知サービスの設定。

環境変数から通知設定を読み込む。

環境変数:
    LINE_NOTIFY_TOKEN: LINE Notify のアクセストークン
    SLACK_WEBHOOK_URL: Slack Incoming Webhook の URL
    NOTIFICATION_CHANNEL: デフォルトの通知チャンネル
        - INTERNAL_LOG (default): ログ出力のみ
        - LINE: LINE Notify
        - SLACK: Slack Webhook
        - ALL: 全チャンネル

Phase 6 で導入。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .schemas import NotificationChannel


@dataclass(frozen=True)
class NotificationSettings:
    """
    通知サービスの設定値。

    環境変数から読み込んだ設定を保持する。
    """

    line_notify_token: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    default_channel: NotificationChannel = NotificationChannel.INTERNAL_LOG

    @property
    def is_line_configured(self) -> bool:
        """LINE Notify が設定されているかどうか。"""
        return bool(self.line_notify_token)

    @property
    def is_slack_configured(self) -> bool:
        """Slack Webhook が設定されているかどうか。"""
        return bool(self.slack_webhook_url)


def _parse_notification_channel(value: Optional[str]) -> NotificationChannel:
    """
    文字列から NotificationChannel を解析する。

    Args:
        value: チャンネル名（大文字小文字不問）

    Returns:
        NotificationChannel: 解析結果（不正な場合は INTERNAL_LOG）
    """
    if not value:
        return NotificationChannel.INTERNAL_LOG

    # Enum値は小文字（"line", "slack", "internal_log"）
    # 入力は大文字小文字不問で受け付ける
    value_lower = value.lower()

    # INTERNAL_LOG は "internal_log"、LINE は "line" など
    # アンダースコアを含む場合も考慮
    if value_lower == "internal_log":
        return NotificationChannel.INTERNAL_LOG

    try:
        return NotificationChannel(value_lower)
    except ValueError:
        # 不正な値の場合はデフォルト
        return NotificationChannel.INTERNAL_LOG


def load_notification_settings() -> NotificationSettings:
    """
    環境変数から通知設定を読み込む。

    Returns:
        NotificationSettings: 読み込んだ設定

    Note:
        - トークン/URL が空文字の場合は None として扱う
        - 無効なチャンネル名の場合は INTERNAL_LOG がデフォルト
    """
    line_token = os.getenv("LINE_NOTIFY_TOKEN") or None
    slack_url = os.getenv("SLACK_WEBHOOK_URL") or None
    channel_str = os.getenv("NOTIFICATION_CHANNEL")

    return NotificationSettings(
        line_notify_token=line_token,
        slack_webhook_url=slack_url,
        default_channel=_parse_notification_channel(channel_str),
    )


# グローバルな設定インスタンス（遅延初期化）
_settings: Optional[NotificationSettings] = None


def get_notification_settings() -> NotificationSettings:
    """
    グローバルな NotificationSettings インスタンスを取得する。

    Returns:
        NotificationSettings: 通知設定

    Note:
        - 初回呼び出し時に環境変数から読み込む
        - 以降は同じインスタンスを返す
    """
    global _settings
    if _settings is None:
        _settings = load_notification_settings()
    return _settings


def reset_notification_settings() -> None:
    """
    通知設定をリセットする（テスト用）。

    次回 get_notification_settings() 呼び出し時に再読み込みする。
    """
    global _settings
    _settings = None
