# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
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
    TWILIO_ACCOUNT_SID: Twilio Account SID (AC...)
    TWILIO_AUTH_TOKEN: Twilio Auth Token（ログ出力厳禁）
    TWILIO_FROM_NUMBER: Twilio 発信元電話番号 (+1...)
    TWILIO_ONCALL_PHONE: オンコール担当者の着信先電話番号 (+81...)
    ONCALL_START_HOUR: オンコール開始時刻 JST (デフォルト: 9)
    ONCALL_END_HOUR: オンコール終了時刻 JST (デフォルト: 22)
    ESCALATION_THRESHOLD: Slack 連続失敗エスカレーション閾値 (デフォルト: 5)
    ESCALATION_COOLDOWN_MINUTES: エスカレーション後クールダウン分数 (デフォルト: 30)

Phase 6 で導入。Twilio / エスカレーション設定は本 PR で追加。
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
    line_channel_access_token: str = ""
    line_user_id: str = ""
    # Twilio オンコール設定
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from_number: Optional[str] = None
    twilio_oncall_phone: Optional[str] = None
    oncall_start_hour: int = 9
    oncall_end_hour: int = 22
    escalation_threshold: int = 5
    escalation_cooldown_minutes: int = 30

    @property
    def is_line_configured(self) -> bool:
        """LINE Notify が設定されているかどうか。"""
        return bool(self.line_notify_token)

    @property
    def is_slack_configured(self) -> bool:
        """Slack Webhook が設定されているかどうか。"""
        return bool(self.slack_webhook_url)

    @property
    def is_line_messaging_configured(self) -> bool:
        """LINE Messaging API が設定されているかどうか。"""
        return bool(self.line_channel_access_token) and bool(self.line_user_id)

    @property
    def is_twilio_configured(self) -> bool:
        """Twilio が使用可能か (SID / Token / From / To の 4 項目必須)。"""
        return all(
            [
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_from_number,
                self.twilio_oncall_phone,
            ]
        )


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
    line_channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
    line_user_id = os.getenv("LINE_USER_ID") or ""
    # Twilio
    twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID") or None
    twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN") or None
    twilio_from_number = os.getenv("TWILIO_FROM_NUMBER") or None
    twilio_oncall_phone = os.getenv("TWILIO_ONCALL_PHONE") or None
    oncall_start_hour = int(os.getenv("ONCALL_START_HOUR", "9"))
    oncall_end_hour = int(os.getenv("ONCALL_END_HOUR", "22"))
    escalation_threshold = int(os.getenv("ESCALATION_THRESHOLD", "5"))
    escalation_cooldown_minutes = int(os.getenv("ESCALATION_COOLDOWN_MINUTES", "30"))

    return NotificationSettings(
        line_notify_token=line_token,
        slack_webhook_url=slack_url,
        default_channel=_parse_notification_channel(channel_str),
        line_channel_access_token=line_channel_access_token,
        line_user_id=line_user_id,
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token,
        twilio_from_number=twilio_from_number,
        twilio_oncall_phone=twilio_oncall_phone,
        oncall_start_hour=oncall_start_hour,
        oncall_end_hour=oncall_end_hour,
        escalation_threshold=escalation_threshold,
        escalation_cooldown_minutes=escalation_cooldown_minutes,
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
