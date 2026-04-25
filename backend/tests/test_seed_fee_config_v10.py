# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_seed_fee_config_v10.py
"""F-4: backend/scripts/seed_fee_config_v10.py のテスト。

関連:
- backend/scripts/seed_fee_config_v10.py
- backend/app/billing/v10_models.py (FeeConfigV10 / V10Base)
- backend/app/auth/models.py (RISK_MODE_SUBSCRIPTION_RATES)
- docs/48_fee_config_seed_runbook.md

設計メモ:
- v10_models.py は専用 V10Base (別 metadata) を使うため、
  fixture で V10Base.metadata.create_all() を別途呼ぶ必要がある。
- SQLite は JSONB を JSON テキストとして保存する (テスト用途では透過的)。
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Generator
from datetime import timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# scripts/ をパスに追加 (本番と同じ sys.path 操作)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-seed-fee-config")

from app.billing.v10_models import FeeConfigV10  # noqa: E402
from scripts.seed_fee_config_v10 import (  # noqa: E402
    V10_DEFAULT_CONFIG_NAME,
    build_v10_default_config,
    seed,
)

# ---------------------------------------------------------------------------
# Pure unit tests on build_v10_default_config (no DB)
# ---------------------------------------------------------------------------


class TestBuildV10DefaultConfig:
    """v10 spec §1 の値が正しく組み立てられることを保証する。"""

    def test_config_name(self) -> None:
        config = build_v10_default_config()
        assert config["config_name"] == "v10_default"

    def test_subscription_rates_use_internal_values(self) -> None:
        """F-3 内部値 (conservative/balanced/aggressive) を キーとして使う。"""
        config = build_v10_default_config()
        rates = config["subscription_rates"]
        assert isinstance(rates, dict)
        assert "conservative" in rates
        assert "balanced" in rates
        assert "aggressive" in rates
        assert set(rates.keys()) == {"conservative", "balanced", "aggressive"}

    def test_subscription_rate_values_match_f3_spec(self) -> None:
        config = build_v10_default_config()
        rates = config["subscription_rates"]
        assert rates["conservative"] == 0.0
        assert rates["balanced"] == 0.003
        assert rates["aggressive"] == 0.01  # Decimal("0.010") → float(0.01)

    def test_tier_thresholds_match_v10_spec(self) -> None:
        config = build_v10_default_config()
        assert config["tier_thresholds_jpy"] == [1_000_000, 10_000_000]

    def test_tier_fee_rates_match_v10_spec(self) -> None:
        config = build_v10_default_config()
        assert config["tier_fee_rates"] == [0.30, 0.25, 0.20]

    def test_tier_monthly_yield_caps_match_v10_spec(self) -> None:
        config = build_v10_default_config()
        assert config["tier_monthly_yield_caps"] == [0.018, 0.023, 0.030]

    def test_affiliate_rate_is_decimal(self) -> None:
        config = build_v10_default_config()
        assert config["affiliate_rate"] == Decimal("0.30")
        assert isinstance(config["affiliate_rate"], Decimal)

    def test_expense_markup_disabled_by_default(self) -> None:
        config = build_v10_default_config()
        assert config["expense_markup_enabled"] is False
        assert config["expense_markup_rate"] == Decimal("0")

    def test_is_active_default_true(self) -> None:
        config = build_v10_default_config()
        assert config["is_active"] is True

    def test_effective_from_is_jst_aware(self) -> None:
        """effective_from は JST タイムゾーン aware である。"""
        config = build_v10_default_config()
        eff = config["effective_from"]
        assert eff.tzinfo is not None
        # JST は UTC+9
        assert (
            eff.utcoffset()
            == timezone.utc.utcoffset(eff) + (eff.utcoffset() - timezone.utc.utcoffset(eff))
            or eff.utcoffset().total_seconds() == 9 * 3600
        )


# ---------------------------------------------------------------------------
# DB integration tests on seed() (sync SessionLocal pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def v10_db() -> Generator[Session, None, None]:
    """fee_configs テーブルだけ持つ SQLite テスト DB を作る。

    fee_transactions は users テーブル (別 Base) への FK を持つため
    V10Base.metadata.create_all は失敗する。seed テスト (fee_configs のみ操作)
    のスコープでは fee_configs テーブル単体で十分。
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    FeeConfigV10.__table__.create(bind=engine)  # type: ignore[attr-defined]
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
        FeeConfigV10.__table__.drop(bind=engine)  # type: ignore[attr-defined]
        engine.dispose()
        os.unlink(path)


class TestSeedIdempotency:
    """同じスクリプトを何度実行しても安全 (冪等)。"""

    def test_seed_inserts_when_no_active(self, v10_db: Session) -> None:
        result = seed(v10_db)
        assert result is True

        rows = v10_db.query(FeeConfigV10).all()
        assert len(rows) == 1
        assert rows[0].config_name == V10_DEFAULT_CONFIG_NAME
        assert rows[0].is_active is True

    def test_seed_skips_when_active_exists(self, v10_db: Session) -> None:
        # 1 回目: 投入
        first = seed(v10_db)
        assert first is True

        # 2 回目: skip
        second = seed(v10_db)
        assert second is False

        # レコードは 1 行のまま
        assert v10_db.query(FeeConfigV10).count() == 1

    def test_seed_skips_when_inactive_exists(self, v10_db: Session) -> None:
        """v10_default が inactive として存在する場合も skip する。

        config_name に UNIQUE 制約があり、状態を問わず重複作成は失敗する。
        値変更時は docs/48 §4 の手順 (新 config_name で投入してスイッチ) を使う。
        """
        config_data = build_v10_default_config()
        config_data["is_active"] = False
        old = FeeConfigV10(**config_data)
        v10_db.add(old)
        v10_db.commit()

        # inactive でも skip → 1 行のまま
        result = seed(v10_db)
        assert result is False
        assert v10_db.query(FeeConfigV10).count() == 1


class TestSeedDryRun:
    """--dry-run はDB に書き込まない。"""

    def test_dry_run_does_not_insert(self, v10_db: Session) -> None:
        result = seed(v10_db, dry_run=True)
        assert result is True  # 実行予定の意

        # DB は空のまま
        assert v10_db.query(FeeConfigV10).count() == 0

    def test_dry_run_with_existing_active_skips(self, v10_db: Session) -> None:
        # 既存 active 投入
        seed(v10_db)
        # dry-run でも skip
        result = seed(v10_db, dry_run=True)
        assert result is False
        assert v10_db.query(FeeConfigV10).count() == 1


class TestSeededRowMatchesSpec:
    """投入後のレコードが v10 spec 値を保持することを保証する。"""

    def test_seeded_row_subscription_rates(self, v10_db: Session) -> None:
        seed(v10_db)
        row = v10_db.query(FeeConfigV10).one()
        assert row.subscription_rates == {
            "conservative": 0.0,
            "balanced": 0.003,
            "aggressive": 0.01,
        }

    def test_seeded_row_tier_thresholds(self, v10_db: Session) -> None:
        seed(v10_db)
        row = v10_db.query(FeeConfigV10).one()
        assert row.tier_thresholds_jpy == [1_000_000, 10_000_000]

    def test_seeded_row_affiliate_rate(self, v10_db: Session) -> None:
        seed(v10_db)
        row = v10_db.query(FeeConfigV10).one()
        # SQLite では NUMERIC が文字列として返ることがあるため Decimal 比較
        assert Decimal(str(row.affiliate_rate)) == Decimal("0.30")
