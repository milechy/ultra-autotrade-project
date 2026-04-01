# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Tests for API key log masking utility.
"""

from __future__ import annotations

import pytest

from app.utils.masking import is_sensitive_key, mask_env_value, mask_key


class TestMaskKey:
    """Tests for mask_key()."""

    def test_long_key_masked(self) -> None:
        result = mask_key("sk-abcdefg1234567890")
        assert result == "sk-abc...7890"

    def test_short_key_fully_masked(self) -> None:
        result = mask_key("short")
        assert result == "***"

    def test_exactly_threshold_length_fully_masked(self) -> None:
        # exactly prefix_len + suffix_len = 10 chars → "***"
        result = mask_key("0123456789")
        assert result == "***"

    def test_one_more_than_threshold_masked(self) -> None:
        # 11 chars → partially masked
        result = mask_key("01234567890")
        assert result == "012345...7890"

    def test_custom_prefix_suffix_lengths(self) -> None:
        result = mask_key("abcdefghij1234", prefix_len=3, suffix_len=2)
        assert result == "abc...34"

    def test_empty_string_fully_masked(self) -> None:
        result = mask_key("")
        assert result == "***"

    def test_prefix_and_suffix_retained(self) -> None:
        key = "ABCDEF_middle_part_WXYZ"
        result = mask_key(key)
        assert result.startswith("ABCDEF")
        assert result.endswith("WXYZ")
        assert "..." in result

    def test_prefix_suffix_not_overlapping(self) -> None:
        key = "A" * 6 + "B" * 4  # exactly 10 = prefix + suffix → "***"
        result = mask_key(key)
        assert result == "***"


class TestIsSensitiveKey:
    """Tests for is_sensitive_key()."""

    @pytest.mark.parametrize(
        "name",
        [
            "API_KEY",
            "OPENAI_API_KEY",
            "SECRET",
            "DB_PASSWORD",
            "JWT_TOKEN",
            "SLACK_WEBHOOK_URL",
            "PRIVATE_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "CREDENTIAL",
            "api-key",
            "api_key",
        ],
    )
    def test_sensitive_names_detected(self, name: str) -> None:
        assert is_sensitive_key(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "DATABASE_URL",
            "LOG_LEVEL",
            "PORT",
            "HOST",
            "DEBUG",
            "APP_NAME",
            "ENVIRONMENT",
        ],
    )
    def test_non_sensitive_names_not_detected(self, name: str) -> None:
        assert is_sensitive_key(name) is False


class TestMaskEnvValue:
    """Tests for mask_env_value()."""

    def test_sensitive_key_masked(self) -> None:
        result = mask_env_value("API_KEY", "sk-abcdefg1234567890")
        assert result == "sk-abc...7890"

    def test_non_sensitive_key_not_masked(self) -> None:
        result = mask_env_value("DATABASE_URL", "postgresql://localhost/mydb")
        assert result == "postgresql://localhost/mydb"

    def test_webhook_masked(self) -> None:
        result = mask_env_value("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/ABCDEFGHIJ")
        assert "..." in result
        assert result != "https://hooks.slack.com/services/ABCDEFGHIJ"

    def test_token_masked(self) -> None:
        result = mask_env_value("INTERNAL_API_TOKEN", "supersecrettoken1234")
        assert result == "supers...1234"

    def test_empty_value_fully_masked(self) -> None:
        result = mask_env_value("API_KEY", "")
        assert result == "***"
