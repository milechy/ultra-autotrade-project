# backend/tests/aave/test_risk_limiter.py
"""Unit tests for risk_limiter module (F-17a)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.aave.risk_limiter import (
    COOLDOWN_HARD_MIN_SECONDS,
    COOLDOWN_STRICT_DEFAULT_SECONDS,
    DAILY_TRADE_PCT_HARD_MAX,
    DAILY_TRADE_PCT_STRICT_DEFAULT,
    HF_HARD_MIN,
    HF_STRICT_DEFAULT,
    SINGLE_TRADE_PCT_HARD_MAX,
    SINGLE_TRADE_PCT_STRICT_DEFAULT,
    get_effective_limits,
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CUSTOM_LIMITER_ENABLED",
        "CUSTOM_LIMITER_EXPIRES_ON",
        "CUSTOM_HF_MIN",
        "CUSTOM_SINGLE_TRADE_PCT",
        "CUSTOM_DAILY_TRADE_PCT",
        "CUSTOM_COOLDOWN_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)


# ---- strict mode (default) ----


def test_returns_strict_defaults_when_disabled(monkeypatch):
    _clear_env(monkeypatch)
    limits = get_effective_limits()
    assert limits.is_custom is False
    assert limits.hf_min == HF_STRICT_DEFAULT
    assert limits.single_trade_pct_max == SINGLE_TRADE_PCT_STRICT_DEFAULT
    assert limits.daily_trade_pct_max == DAILY_TRADE_PCT_STRICT_DEFAULT
    assert limits.cooldown_seconds == COOLDOWN_STRICT_DEFAULT_SECONDS


def test_disabled_when_enabled_false(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "false")
    limits = get_effective_limits()
    assert limits.is_custom is False


# ---- expiry ----


def test_reverts_to_strict_when_expired(monkeypatch):
    _clear_env(monkeypatch)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", yesterday)
    limits = get_effective_limits()
    assert limits.is_custom is False
    assert limits.hf_min == HF_STRICT_DEFAULT


def test_active_when_not_expired(monkeypatch):
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    limits = get_effective_limits()
    assert limits.is_custom is True
    assert limits.expires_on == date.today() + timedelta(days=1)


# ---- custom values ----


def test_custom_values_applied(monkeypatch):
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_HF_MIN", "1.3")
    monkeypatch.setenv("CUSTOM_SINGLE_TRADE_PCT", "20")
    monkeypatch.setenv("CUSTOM_DAILY_TRADE_PCT", "60")
    monkeypatch.setenv("CUSTOM_COOLDOWN_SECONDS", "120")

    limits = get_effective_limits()
    assert limits.hf_min == Decimal("1.3")
    assert limits.single_trade_pct_max == Decimal("20")
    assert limits.daily_trade_pct_max == Decimal("60")
    assert limits.cooldown_seconds == 120


# ---- hard limits enforcement ----


def test_hf_hard_floor_enforced(monkeypatch):
    """Custom HF below 1.2 must be clamped to 1.2."""
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_HF_MIN", "0.9")  # below hard floor

    limits = get_effective_limits()
    assert limits.hf_min == HF_HARD_MIN  # clamped to 1.2


def test_single_trade_hard_ceiling_enforced(monkeypatch):
    """Custom single trade % above 40% must be clamped to 40%."""
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_SINGLE_TRADE_PCT", "99")  # above hard ceiling

    limits = get_effective_limits()
    assert limits.single_trade_pct_max == SINGLE_TRADE_PCT_HARD_MAX  # clamped to 40


def test_daily_trade_hard_ceiling_enforced(monkeypatch):
    """Custom daily trade % above 90% must be clamped to 90%."""
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_DAILY_TRADE_PCT", "100")  # above hard ceiling

    limits = get_effective_limits()
    assert limits.daily_trade_pct_max == DAILY_TRADE_PCT_HARD_MAX  # clamped to 90


def test_cooldown_hard_floor_enforced(monkeypatch):
    """Custom cooldown below 60s must be clamped to 60s."""
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_COOLDOWN_SECONDS", "10")  # below hard floor

    limits = get_effective_limits()
    assert limits.cooldown_seconds == COOLDOWN_HARD_MIN_SECONDS  # clamped to 60


# ---- invalid env var handling ----


def test_invalid_hf_falls_back_to_strict(monkeypatch):
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_HF_MIN", "not-a-number")

    limits = get_effective_limits()
    # Fallback to strict default, then max with hard floor → HF_STRICT_DEFAULT
    assert limits.hf_min == HF_STRICT_DEFAULT


def test_invalid_cooldown_falls_back_to_strict(monkeypatch):
    _clear_env(monkeypatch)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setenv("CUSTOM_LIMITER_ENABLED", "true")
    monkeypatch.setenv("CUSTOM_LIMITER_EXPIRES_ON", tomorrow)
    monkeypatch.setenv("CUSTOM_COOLDOWN_SECONDS", "xyz")

    limits = get_effective_limits()
    assert limits.cooldown_seconds == COOLDOWN_STRICT_DEFAULT_SECONDS


# ---- EffectiveLimits is frozen dataclass ----


def test_effective_limits_is_immutable(monkeypatch):
    _clear_env(monkeypatch)
    limits = get_effective_limits()
    with pytest.raises((AttributeError, TypeError)):
        limits.hf_min = Decimal("99")  # type: ignore[misc]


# ---- hard limit constants are correct ----


def test_hard_limit_constants():
    assert HF_HARD_MIN == Decimal("1.2")
    assert SINGLE_TRADE_PCT_HARD_MAX == Decimal("40")
    assert DAILY_TRADE_PCT_HARD_MAX == Decimal("90")
    assert COOLDOWN_HARD_MIN_SECONDS == 60
