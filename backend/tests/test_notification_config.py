# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_notification_config.py

"""
通知設定のユニットテスト。
"""

import os
from unittest.mock import patch

from app.notifications.config import (
    NotificationSettings,
    _parse_notification_channel,
    _parse_severity,
    get_notification_settings,
    load_notification_settings,
    reset_notification_settings,
)
from app.notifications.schemas import NotificationChannel, NotificationSeverity


class TestParseNotificationChannel:
    """_parse_notification_channel 関数のテスト"""

    def test_parse_internal_log(self):
        """INTERNAL_LOG が正しく解析されることを確認"""
        assert _parse_notification_channel("INTERNAL_LOG") == NotificationChannel.INTERNAL_LOG

    def test_parse_line(self):
        """LINE が正しく解析されることを確認"""
        assert _parse_notification_channel("LINE") == NotificationChannel.LINE

    def test_parse_slack(self):
        """SLACK が正しく解析されることを確認"""
        assert _parse_notification_channel("SLACK") == NotificationChannel.SLACK

    def test_parse_lowercase(self):
        """小文字でも正しく解析されることを確認"""
        assert _parse_notification_channel("line") == NotificationChannel.LINE
        assert _parse_notification_channel("slack") == NotificationChannel.SLACK

    def test_parse_none_returns_default(self):
        """None の場合はデフォルト値を返すことを確認"""
        assert _parse_notification_channel(None) == NotificationChannel.INTERNAL_LOG

    def test_parse_empty_returns_default(self):
        """空文字の場合はデフォルト値を返すことを確認"""
        assert _parse_notification_channel("") == NotificationChannel.INTERNAL_LOG

    def test_parse_invalid_returns_default(self):
        """無効な値の場合はデフォルト値を返すことを確認"""
        assert _parse_notification_channel("INVALID") == NotificationChannel.INTERNAL_LOG
        assert _parse_notification_channel("webhook") == NotificationChannel.INTERNAL_LOG

    def test_parse_sms_returns_sms(self):
        """sms チャンネルが正しくパースされることを確認（Twilio SMS 追加）"""
        assert _parse_notification_channel("sms") == NotificationChannel.SMS
        assert _parse_notification_channel("SMS") == NotificationChannel.SMS

    def test_parse_phone_returns_phone(self):
        """phone チャンネルが正しくパースされることを確認（Twilio 音声 追加）"""
        assert _parse_notification_channel("phone") == NotificationChannel.PHONE
        assert _parse_notification_channel("PHONE") == NotificationChannel.PHONE


class TestNotificationSettings:
    """NotificationSettings クラスのテスト"""

    def test_is_line_configured_true(self):
        """LINE トークンが設定されている場合"""
        settings = NotificationSettings(line_notify_token="test-token")
        assert settings.is_line_configured is True

    def test_is_line_configured_false(self):
        """LINE トークンが未設定の場合"""
        settings = NotificationSettings(line_notify_token=None)
        assert settings.is_line_configured is False

    def test_is_slack_configured_true(self):
        """Slack URL が設定されている場合"""
        settings = NotificationSettings(slack_webhook_url="https://hooks.slack.com/xxx")
        assert settings.is_slack_configured is True

    def test_is_slack_configured_false(self):
        """Slack URL が未設定の場合"""
        settings = NotificationSettings(slack_webhook_url=None)
        assert settings.is_slack_configured is False

    def test_default_channel(self):
        """デフォルトチャンネルが INTERNAL_LOG であることを確認"""
        settings = NotificationSettings()
        assert settings.default_channel == NotificationChannel.INTERNAL_LOG


class TestLoadNotificationSettings:
    """load_notification_settings 関数のテスト"""

    def test_load_with_all_env_vars(self):
        """全ての環境変数が設定されている場合"""
        with patch.dict(
            os.environ,
            {
                "LINE_NOTIFY_TOKEN": "test-line-token",
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
                "NOTIFICATION_CHANNEL": "SLACK",
            },
        ):
            settings = load_notification_settings()

            assert settings.line_notify_token == "test-line-token"
            assert settings.slack_webhook_url == "https://hooks.slack.com/test"
            assert settings.default_channel == NotificationChannel.SLACK

    def test_load_with_no_env_vars(self):
        """環境変数が未設定の場合"""
        with patch.dict(os.environ, {}, clear=True):
            # 他の環境変数の影響を排除
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ["LINE_NOTIFY_TOKEN", "SLACK_WEBHOOK_URL", "NOTIFICATION_CHANNEL"]
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_notification_settings()

                assert settings.line_notify_token is None
                assert settings.slack_webhook_url is None
                assert settings.default_channel == NotificationChannel.INTERNAL_LOG

    def test_load_with_empty_values(self):
        """空文字が設定されている場合は None として扱う"""
        with patch.dict(
            os.environ,
            {
                "LINE_NOTIFY_TOKEN": "",
                "SLACK_WEBHOOK_URL": "",
                "NOTIFICATION_CHANNEL": "",
            },
        ):
            settings = load_notification_settings()

            assert settings.line_notify_token is None
            assert settings.slack_webhook_url is None
            assert settings.default_channel == NotificationChannel.INTERNAL_LOG


class TestParseSeverity:
    """_parse_severity 関数のテスト (LINE_MIN_SEVERITY 用)"""

    def test_parse_warning(self):
        assert (
            _parse_severity("warning", NotificationSeverity.ALERT) == NotificationSeverity.WARNING
        )

    def test_parse_alert_uppercase(self):
        assert _parse_severity("ALERT", NotificationSeverity.ALERT) == NotificationSeverity.ALERT

    def test_parse_none_returns_default(self):
        assert _parse_severity(None, NotificationSeverity.ALERT) == NotificationSeverity.ALERT

    def test_parse_empty_returns_default(self):
        assert _parse_severity("", NotificationSeverity.ALERT) == NotificationSeverity.ALERT

    def test_parse_invalid_returns_default(self):
        assert _parse_severity("bogus", NotificationSeverity.ALERT) == NotificationSeverity.ALERT


class TestLoadNotificationSettingsLineMinSeverity:
    """LINE_MIN_SEVERITY env var の解釈テスト"""

    def test_load_line_min_severity_default_alert(self):
        """LINE_MIN_SEVERITY 未設定 → ALERT (既定挙動を維持)。"""
        env = {k: v for k, v in os.environ.items() if k != "LINE_MIN_SEVERITY"}
        with patch.dict(os.environ, env, clear=True):
            settings = load_notification_settings()
            assert settings.line_min_severity == NotificationSeverity.ALERT

    def test_load_line_min_severity_warning_opt_in(self):
        """LINE_MIN_SEVERITY=warning → WARNING (AI proposal opt-in)。"""
        with patch.dict(os.environ, {"LINE_MIN_SEVERITY": "warning"}):
            settings = load_notification_settings()
            assert settings.line_min_severity == NotificationSeverity.WARNING

    def test_load_line_min_severity_invalid_falls_back(self):
        """不正な LINE_MIN_SEVERITY → ALERT にフォールバック。"""
        with patch.dict(os.environ, {"LINE_MIN_SEVERITY": "loud"}):
            settings = load_notification_settings()
            assert settings.line_min_severity == NotificationSeverity.ALERT


class TestGetNotificationSettings:
    """get_notification_settings 関数のテスト"""

    def test_returns_singleton(self):
        """シングルトンインスタンスを返すことを確認"""
        reset_notification_settings()

        settings1 = get_notification_settings()
        settings2 = get_notification_settings()

        assert settings1 is settings2

    def test_reset_clears_singleton(self):
        """reset 後は新しいインスタンスが生成されることを確認"""
        get_notification_settings()
        reset_notification_settings()
        settings2 = get_notification_settings()

        assert settings2 is not None
