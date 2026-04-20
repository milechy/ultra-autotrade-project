# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_ai_config_validation.py
"""Tests for AI model config validation (startup guard against deprecated models)."""

import os
from unittest import mock

import pytest

from app.ai.config import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_FALLBACK_MODEL,
    DEPRECATED_CLAUDE_MODELS,
    VALID_CLAUDE_MODELS,
    _validate_model_config,
)


def test_default_model_is_not_deprecated() -> None:
    assert DEFAULT_CLAUDE_MODEL not in DEPRECATED_CLAUDE_MODELS
    assert DEFAULT_FALLBACK_MODEL not in DEPRECATED_CLAUDE_MODELS


def test_default_model_is_in_valid_list() -> None:
    assert DEFAULT_CLAUDE_MODEL in VALID_CLAUDE_MODELS
    assert DEFAULT_FALLBACK_MODEL in VALID_CLAUDE_MODELS


@mock.patch.dict(os.environ, {"AI_CLAUDE_MODEL": "claude-sonnet-4-20250514"})
def test_deprecated_primary_model_raises_at_startup() -> None:
    with pytest.raises(ValueError, match="Deprecated Claude model"):
        _validate_model_config()


@mock.patch.dict(os.environ, {"AI_FALLBACK_MODEL": "claude-3-5-sonnet-latest"})
def test_deprecated_fallback_model_raises_at_startup() -> None:
    with pytest.raises(ValueError, match="Deprecated Claude model"):
        _validate_model_config()


@mock.patch.dict(
    os.environ,
    {
        "AI_CLAUDE_MODEL": "claude-sonnet-4-6-20250929",
        "AI_FALLBACK_MODEL": "claude-haiku-4-5-20251001",
    },
)
def test_valid_models_pass_validation() -> None:
    _validate_model_config()  # should not raise


@mock.patch.dict(os.environ, {}, clear=False)
def test_unset_env_vars_use_defaults_and_pass() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("AI_CLAUDE_MODEL", "AI_FALLBACK_MODEL")}
    with mock.patch.dict(os.environ, env, clear=True):
        _validate_model_config()  # defaults are valid, should not raise


@mock.patch.dict(os.environ, {"AI_CLAUDE_MODEL": "claude-opus-4-7"})
def test_opus_model_passes_validation() -> None:
    _validate_model_config()  # should not raise


@mock.patch.dict(os.environ, {"AI_CLAUDE_MODEL": "claude-unknown-99-99"})
def test_unknown_model_is_not_in_deprecated_so_passes() -> None:
    # Unknown models are NOT in DEPRECATED list, so they pass validation.
    # The allowlist check is intentionally permissive to avoid blocking future models.
    _validate_model_config()  # should not raise (deprecated-only check)
