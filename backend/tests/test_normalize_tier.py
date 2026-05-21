# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_normalize_tier.py
"""normalize_tier() ヘルパーのユニットテスト (F-6 / F-13)。"""

import logging
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-normalize-tier")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import pytest  # noqa: E402

from app.auth.models import (  # noqa: E402
    InvestmentTier,
    normalize_tier,
)


class TestNormalizeTierKnownValues:
    """LOWER / MIDDLE / UPPER は enum でそのまま返る。"""

    @pytest.mark.parametrize(
        "raw_value,expected",
        [
            ("LOWER", InvestmentTier.LOWER),
            ("MIDDLE", InvestmentTier.MIDDLE),
            ("UPPER", InvestmentTier.UPPER),
        ],
    )
    def test_normalize_tier_known_value(self, raw_value: str, expected: InvestmentTier) -> None:
        assert normalize_tier(raw_value) == expected


class TestNormalizeTierFallback:
    """不明値 / None は WARNING ログ + LOWER フォールバック (ValueError は raise しない)。"""

    def test_normalize_tier_unknown_logs_warning_and_returns_lower(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="app.auth.models"):
            result = normalize_tier("INVALID_TIER", user_id=42)
        assert result == InvestmentTier.LOWER
        assert any(
            record.message == "tier_normalize_fallback" and record.levelno == logging.WARNING
            for record in caplog.records
        )
        warning_record = next(r for r in caplog.records if r.message == "tier_normalize_fallback")
        assert warning_record.user_id == 42
        assert warning_record.received_tier == "INVALID_TIER"
        assert warning_record.fallback_to == "LOWER"

    def test_normalize_tier_none_returns_lower(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="app.auth.models"):
            result = normalize_tier(None)
        assert result == InvestmentTier.LOWER
        warning_record = next(r for r in caplog.records if r.message == "tier_normalize_fallback")
        assert warning_record.received_tier is None
        assert warning_record.user_id is None

    def test_normalize_tier_empty_string_falls_back_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="app.auth.models"):
            result = normalize_tier("", user_id=7)
        assert result == InvestmentTier.LOWER
        assert any(r.message == "tier_normalize_fallback" for r in caplog.records)

    def test_normalize_tier_does_not_raise_on_unknown(self) -> None:
        """フォールバック時に ValueError を raise しない (フィー計算継続のため)。"""
        try:
            normalize_tier("XYZ", user_id=1)
        except ValueError as exc:  # pragma: no cover
            pytest.fail(f"normalize_tier should not raise ValueError but got: {exc}")

    def test_normalize_tier_general_falls_back_to_lower_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """F-13: GENERAL は enum から削除済み → 不明値として LOWER にフォールバック。"""
        with caplog.at_level(logging.WARNING, logger="app.auth.models"):
            result = normalize_tier("GENERAL")
        assert result == InvestmentTier.LOWER
        assert any(r.message == "tier_normalize_fallback" for r in caplog.records)
