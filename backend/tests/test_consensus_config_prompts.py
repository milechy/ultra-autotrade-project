# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_consensus_config_prompts.py
"""Tests for the 4-axis consensus config fields (EPIC-1 1-5) and the v6 prompt
template (EPIC-1 1-8), plus the consensus weight startup validation.

Covered:
- env default values (shadow / 0.40 / 65)
- CONSENSUS_4AXIS_MODE invalid value -> RuntimeError (fail-closed)
- consensus_score_threshold is Decimal-typed
- PROMPT_REGISTRY["v6"] exists, is frozen, and shares v5's placeholder set
- startup validation does not raise for DEFAULT_WEIGHTS, raises for broken weights
"""

import dataclasses
import importlib
import os
import string
from decimal import Decimal
from unittest.mock import patch

import pytest


def _reload_config():
    from app.ai import config as ai_config

    importlib.reload(ai_config)
    return ai_config


def _placeholders(template: str) -> set[str]:
    """Extract the set of {name} placeholders from a .format-style template."""
    return {field_name for _, field_name, _, _ in string.Formatter().parse(template) if field_name}


class TestConsensusConfigDefaults:
    """Default env values for the 4-axis consensus settings."""

    def test_default_values_shadow_040_65(self):
        """CONSENSUS_* env unset -> shadow / Decimal('0.40') / 65."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "CONSENSUS_4AXIS_MODE",
                "CONSENSUS_SCORE_THRESHOLD",
                "CONSENSUS_CONF_THRESHOLD",
            )
        }
        with patch.dict(os.environ, env, clear=True):
            ai_config = _reload_config()
            settings = ai_config.get_ai_settings()

        assert settings.consensus_4axis_mode == "shadow"
        assert settings.consensus_score_threshold == Decimal("0.40")
        assert settings.consensus_conf_threshold == 65

    def test_custom_values_override_defaults(self):
        env_overrides = {
            "CONSENSUS_4AXIS_MODE": "on",
            "CONSENSUS_SCORE_THRESHOLD": "0.55",
            "CONSENSUS_CONF_THRESHOLD": "70",
        }
        with patch.dict(os.environ, env_overrides):
            ai_config = _reload_config()
            settings = ai_config.get_ai_settings()

        assert settings.consensus_4axis_mode == "on"
        assert settings.consensus_score_threshold == Decimal("0.55")
        assert settings.consensus_conf_threshold == 70

    @pytest.mark.parametrize("mode", ["off", "shadow", "a_b", "on"])
    def test_all_allowed_modes_accepted(self, mode):
        with patch.dict(os.environ, {"CONSENSUS_4AXIS_MODE": mode}):
            ai_config = _reload_config()
            settings = ai_config.get_ai_settings()
        assert settings.consensus_4axis_mode == mode


class TestConsensusModeFailClosed:
    """CONSENSUS_4AXIS_MODE outside the allow-list must raise (fail-closed)."""

    def test_invalid_mode_raises_runtime_error(self):
        with patch.dict(os.environ, {"CONSENSUS_4AXIS_MODE": "enabled"}):
            ai_config = _reload_config()
            with pytest.raises(RuntimeError, match="Invalid value for env var"):
                ai_config.get_ai_settings()

    def test_helper_rejects_unknown_value(self):
        ai_config = _reload_config()
        with patch.dict(os.environ, {"CONSENSUS_4AXIS_MODE": "ON"}):
            # case-sensitive: "ON" is not in the allow-list
            with pytest.raises(RuntimeError):
                ai_config._get_env_consensus_mode("CONSENSUS_4AXIS_MODE", default="shadow")

    def test_helper_returns_default_when_unset(self):
        ai_config = _reload_config()
        env = {k: v for k, v in os.environ.items() if k != "CONSENSUS_MODE_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert (
                ai_config._get_env_consensus_mode("CONSENSUS_MODE_MISSING", default="off") == "off"
            )


class TestConsensusThresholdType:
    """consensus_score_threshold must be a Decimal (never float)."""

    def test_threshold_is_decimal_instance(self):
        ai_config = _reload_config()
        settings = ai_config.get_ai_settings()
        assert isinstance(settings.consensus_score_threshold, Decimal)

    def test_threshold_custom_value_is_decimal(self):
        with patch.dict(os.environ, {"CONSENSUS_SCORE_THRESHOLD": "0.30"}):
            ai_config = _reload_config()
            settings = ai_config.get_ai_settings()
        assert isinstance(settings.consensus_score_threshold, Decimal)
        assert settings.consensus_score_threshold == Decimal("0.30")

    def test_invalid_threshold_raises_runtime_error(self):
        with patch.dict(os.environ, {"CONSENSUS_SCORE_THRESHOLD": "not_a_decimal"}):
            ai_config = _reload_config()
            with pytest.raises(RuntimeError, match="Invalid decimal value"):
                ai_config.get_ai_settings()


class TestV6PromptTemplate:
    """PROMPT_REGISTRY['v6'] structural requirements."""

    def test_v6_registered(self):
        from app.ai.prompts import PROMPT_REGISTRY

        assert "v6" in PROMPT_REGISTRY
        assert PROMPT_REGISTRY["v6"].version == "v6"

    def test_v6_is_frozen_dataclass_instance(self):
        from app.ai.prompts import PROMPT_REGISTRY, PromptTemplate

        v6 = PROMPT_REGISTRY["v6"]
        assert isinstance(v6, PromptTemplate)
        # frozen dataclass: assignment must raise
        assert dataclasses.fields(PromptTemplate)  # is a dataclass
        with pytest.raises(dataclasses.FrozenInstanceError):
            v6.version = "v7"  # type: ignore[misc]

    def test_v6_placeholders_match_v5(self):
        from app.ai.prompts import PROMPT_REGISTRY

        v5 = PROMPT_REGISTRY["v5"]
        v6 = PROMPT_REGISTRY["v6"]
        assert _placeholders(v6.user_template) == _placeholders(v5.user_template)

    def test_v6_system_mentions_weighted_score_and_threshold(self):
        from app.ai.prompts import PROMPT_REGISTRY

        system = PROMPT_REGISTRY["v6"].system_prompt
        assert "weighted directional score" in system
        assert "0.40" in system
        assert "weighted confidence" in system

    def test_default_version_unchanged(self):
        from app.ai.prompts import DEFAULT_VERSION

        assert DEFAULT_VERSION == "v1"


class TestConsensusWeightStartupValidation:
    """The startup hook's validation logic over DEFAULT_WEIGHTS / broken weights."""

    def test_default_weights_pass_validation(self):
        from app.ai.agents import MultiAgentContext, validate_agent_weights

        # Must not raise.
        validate_agent_weights(MultiAgentContext.DEFAULT_WEIGHTS)

    def test_broken_weights_raise_value_error(self):
        from app.ai.agents import validate_agent_weights

        broken = {
            "risk": Decimal("0.40"),
            "indicator": Decimal("0.25"),
            "macro": Decimal("0.20"),
            "pattern": Decimal("0.50"),  # sum = 1.35, out of tolerance
        }
        with pytest.raises(ValueError):
            validate_agent_weights(broken)


class TestAISettingsHasConsensusFields:
    """AISettings dataclass exposes the new consensus fields."""

    def test_dataclass_field_names(self):
        from app.ai.config import AISettings

        names = {f.name for f in dataclasses.fields(AISettings)}
        assert {
            "consensus_4axis_mode",
            "consensus_score_threshold",
            "consensus_conf_threshold",
        } <= names
