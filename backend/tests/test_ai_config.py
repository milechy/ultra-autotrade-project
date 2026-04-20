# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_ai_config.py
"""Tests for app.ai.config module."""

import os
from unittest.mock import patch


class TestGetEnvInt:
    """Tests for _get_env_int helper."""

    def test_returns_int_when_valid_value_in_env(self):
        from app.ai.config import _get_env_int

        with patch.dict(os.environ, {"TEST_INT_VAR": "42"}):
            result = _get_env_int("TEST_INT_VAR", default=10)
        assert result == 42

    def test_returns_default_when_env_var_not_set(self):
        from app.ai.config import _get_env_int

        env = {k: v for k, v in os.environ.items() if k != "TEST_INT_VAR_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            result = _get_env_int("TEST_INT_VAR_MISSING", default=99)
        assert result == 99

    def test_returns_default_when_env_var_is_empty_string(self):
        from app.ai.config import _get_env_int

        with patch.dict(os.environ, {"TEST_INT_EMPTY": ""}):
            result = _get_env_int("TEST_INT_EMPTY", default=55)
        assert result == 55

    def test_raises_runtime_error_on_invalid_value(self):
        import pytest

        from app.ai.config import _get_env_int

        with patch.dict(os.environ, {"TEST_INT_BAD": "not_a_number"}):
            with pytest.raises(RuntimeError, match="Invalid integer value"):
                _get_env_int("TEST_INT_BAD", default=10)

    def test_raises_runtime_error_on_float_string(self):
        import pytest

        from app.ai.config import _get_env_int

        with patch.dict(os.environ, {"TEST_INT_FLOAT": "3.14"}):
            with pytest.raises(RuntimeError):
                _get_env_int("TEST_INT_FLOAT", default=10)


class TestGetEnvBool:
    """Tests for _get_env_bool helper."""

    def test_returns_true_for_true_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "true"}):
            assert _get_env_bool("TEST_BOOL", default=False) is True

    def test_returns_true_for_1_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "1"}):
            assert _get_env_bool("TEST_BOOL", default=False) is True

    def test_returns_true_for_yes_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "yes"}):
            assert _get_env_bool("TEST_BOOL", default=False) is True

    def test_returns_false_for_false_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "false"}):
            assert _get_env_bool("TEST_BOOL", default=True) is False

    def test_returns_false_for_0_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "0"}):
            assert _get_env_bool("TEST_BOOL", default=True) is False

    def test_returns_false_for_arbitrary_string(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL": "anything_else"}):
            assert _get_env_bool("TEST_BOOL", default=True) is False

    def test_returns_default_when_env_var_not_set(self):
        from app.ai.config import _get_env_bool

        env = {k: v for k, v in os.environ.items() if k != "TEST_BOOL_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert _get_env_bool("TEST_BOOL_MISSING", default=True) is True

    def test_returns_default_when_env_var_is_empty(self):
        from app.ai.config import _get_env_bool

        with patch.dict(os.environ, {"TEST_BOOL_EMPTY": ""}):
            assert _get_env_bool("TEST_BOOL_EMPTY", default=True) is True


class TestGetAISettings:
    """Tests for get_ai_settings() function."""

    def test_default_values_with_dummy_keys_set(self):
        """When optional model vars are not set, defaults are used."""
        env_overrides = {
            "ANTHROPIC_API_KEY": "sk-test-anthropic",
            "OPENAI_API_KEY": "sk-test-openai",
        }
        # Remove model override vars if present, keep only required keys
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "AI_CLAUDE_MODEL",
                "AI_OPENAI_MODEL",
                "AI_MIN_CONFIDENCE_THRESHOLD",
                "AI_CROSS_VALIDATION_ENABLED",
            )
        }
        env.update(env_overrides)

        with patch.dict(os.environ, env, clear=True):
            import importlib

            from app.ai import config as ai_config

            importlib.reload(ai_config)
            settings = ai_config.get_ai_settings()

        assert settings.claude_model == "claude-sonnet-4-6"
        assert settings.openai_model == "gpt-4o"
        assert settings.min_confidence_threshold == 40
        assert settings.cross_validation_enabled is True
        assert settings.anthropic_api_key == "sk-test-anthropic"
        assert settings.openai_api_key == "sk-test-openai"

    def test_custom_model_and_threshold_values(self):
        """Custom env vars override default model and threshold values."""
        env_overrides = {
            "ANTHROPIC_API_KEY": "sk-custom",
            "OPENAI_API_KEY": "sk-openai-custom",
            "AI_CLAUDE_MODEL": "claude-3-opus",
            "AI_OPENAI_MODEL": "gpt-4-turbo",
            "AI_MIN_CONFIDENCE_THRESHOLD": "60",
            "AI_CROSS_VALIDATION_ENABLED": "false",
        }

        with patch.dict(os.environ, env_overrides):
            import importlib

            from app.ai import config as ai_config

            importlib.reload(ai_config)
            settings = ai_config.get_ai_settings()

        assert settings.claude_model == "claude-3-opus"
        assert settings.openai_model == "gpt-4-turbo"
        assert settings.min_confidence_threshold == 60
        assert settings.cross_validation_enabled is False

    def test_api_keys_are_none_when_not_set(self):
        """When API keys are absent, settings fields are None or empty."""
        env = {
            k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
        }

        with patch.dict(os.environ, env, clear=True):
            import importlib

            from app.ai import config as ai_config

            importlib.reload(ai_config)
            settings = ai_config.get_ai_settings()

        # get_env with required=False returns "" when not set, which is falsy
        assert not settings.anthropic_api_key
        assert not settings.openai_api_key

    def test_cross_validation_enabled_true_by_default(self):
        """cross_validation_enabled defaults to True."""
        env = {k: v for k, v in os.environ.items() if k != "AI_CROSS_VALIDATION_ENABLED"}

        with patch.dict(os.environ, env, clear=True):
            import importlib

            from app.ai import config as ai_config

            importlib.reload(ai_config)
            settings = ai_config.get_ai_settings()

        assert settings.cross_validation_enabled is True

    def test_invalid_confidence_threshold_raises_runtime_error(self):
        """An invalid integer for threshold raises RuntimeError."""
        import pytest

        with patch.dict(os.environ, {"AI_MIN_CONFIDENCE_THRESHOLD": "not_an_int"}):
            import importlib

            from app.ai import config as ai_config

            importlib.reload(ai_config)
            with pytest.raises(RuntimeError, match="Invalid integer value"):
                ai_config.get_ai_settings()
