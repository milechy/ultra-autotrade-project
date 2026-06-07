# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_proposals_fee_wiring.py
"""Lane 5: proposals.fee_rate 配線テスト。

非管理型 (non-custodial) submit-tx 経路で fee_model_v10 の tier 別 fee_rate が
proposal に記録されることを確認する。

関連:
- backend/app/proposals/router.py (_lookup_fee_rate_for_user)
- backend/alembic/versions/q7r8s9t0u1v2_proposals_fee_rate_server_default.py
- Asana 1215428893224245
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-lane5-fee-wiring")

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.fees.models import FeeConfigV10  # noqa: E402
from app.proposals.router import _lookup_fee_rate_for_user  # noqa: E402

_JST = timezone(timedelta(hours=9))


@pytest.fixture()
def db_session():
    """SQLite in-memory テスト DB セッション。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    os.close(fd)
    os.unlink(path)


def _insert_user(db: Session, user_id: int, tier: str) -> User:
    user = User(
        id=user_id,
        email=f"user{user_id}@example.com",
        username=f"user{user_id}",
        hashed_password="x",
        tier=tier,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _insert_fee_config(db: Session, *, is_active: bool = True) -> FeeConfigV10:
    config = FeeConfigV10(
        config_name="v10_test",
        tier_thresholds_jpy=[1_000_000, 10_000_000],
        tier_fee_rates=[0.30, 0.25, 0.20],  # LOWER, MIDDLE, UPPER
        tier_monthly_yield_caps=[0.018, 0.023, 0.030],
        subscription_rates={"conservative": 0.0, "balanced": 0.003, "aggressive": 0.01},
        expense_markup_enabled=False,
        expense_markup_rate=Decimal("0"),
        affiliate_rate=Decimal("0.10"),
        is_active=is_active,
        effective_from=datetime(2026, 5, 1, tzinfo=_JST),
    )
    db.add(config)
    db.flush()
    return config


class TestLookupFeeRateForUser:
    """_lookup_fee_rate_for_user ヘルパーのユニットテスト。"""

    def test_lower_tier_returns_30_percent(self, db_session: Session) -> None:
        _insert_user(db_session, user_id=1, tier="LOWER")
        _insert_fee_config(db_session)
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=1)
        assert rate == Decimal("0.30"), f"LOWER tier should yield 0.30, got {rate}"

    def test_middle_tier_returns_25_percent(self, db_session: Session) -> None:
        _insert_user(db_session, user_id=2, tier="MIDDLE")
        _insert_fee_config(db_session)
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=2)
        assert rate == Decimal("0.25"), f"MIDDLE tier should yield 0.25, got {rate}"

    def test_upper_tier_returns_20_percent(self, db_session: Session) -> None:
        _insert_user(db_session, user_id=3, tier="UPPER")
        _insert_fee_config(db_session)
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=3)
        assert rate == Decimal("0.20"), f"UPPER tier should yield 0.20, got {rate}"

    def test_no_active_config_returns_zero(self, db_session: Session) -> None:
        _insert_user(db_session, user_id=4, tier="LOWER")
        _insert_fee_config(db_session, is_active=False)
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=4)
        assert rate == Decimal("0"), "No active config should return 0 (fail-open)"

    def test_user_not_found_returns_zero(self, db_session: Session) -> None:
        _insert_fee_config(db_session)
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=999)
        assert rate == Decimal("0"), "Missing user should return 0 (fail-open)"

    def test_no_config_at_all_returns_zero(self, db_session: Session) -> None:
        _insert_user(db_session, user_id=5, tier="LOWER")
        db_session.commit()

        rate = _lookup_fee_rate_for_user(db_session, user_id=5)
        assert rate == Decimal("0"), "No config at all should return 0 (fail-open)"
