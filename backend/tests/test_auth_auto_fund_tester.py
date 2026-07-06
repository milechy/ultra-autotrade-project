# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_auth_auto_fund_tester.py
"""staging-v4 テスター自動資金割当 (_auto_fund_tester_if_enabled) のテスト。"""

import os
import tempfile
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-auth-tests")

from app.auth.models import User, UserRole
from app.auth.router import _auto_fund_tester_if_enabled
from app.database import Base
from app.partner.allocation_models import FundAllocation


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _make_tester(db: Session, email: str = "tester@example.com") -> User:
    user = User(
        email=email,
        username=email.split("@")[0],
        hashed_password="x",
        role=UserRole.VIEWER.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestAutoFundTesterIfEnabled:
    def test_noop_when_env_unset(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTO_FUND_PARTNER_ID/AMOUNT が未設定なら何も作らない。"""
        monkeypatch.delenv("AUTO_FUND_PARTNER_ID", raising=False)
        monkeypatch.delenv("AUTO_FUND_TESTER_ALLOCATION_USD", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        user = _make_tester(db)

        _auto_fund_tester_if_enabled(db, user)

        assert db.query(FundAllocation).count() == 0

    def test_creates_allocation_when_enabled(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """有効時は指定額の active FundAllocation が1件作られる。"""
        monkeypatch.setenv("AUTO_FUND_PARTNER_ID", "9")
        monkeypatch.setenv("AUTO_FUND_TESTER_ALLOCATION_USD", "150000")
        monkeypatch.delenv("APP_ENV", raising=False)
        user = _make_tester(db)

        _auto_fund_tester_if_enabled(db, user)

        allocations = db.query(FundAllocation).all()
        assert len(allocations) == 1
        assert allocations[0].tester_user_id == user.id
        assert allocations[0].partner_id == 9
        assert allocations[0].status == "active"
        assert allocations[0].allocated_amount_usd == 150000

    def test_no_duplicate_when_active_allocation_exists(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """既にactiveなallocationがあれば重複作成しない(terms再同意対策)。"""
        monkeypatch.setenv("AUTO_FUND_PARTNER_ID", "9")
        monkeypatch.setenv("AUTO_FUND_TESTER_ALLOCATION_USD", "150000")
        monkeypatch.delenv("APP_ENV", raising=False)
        user = _make_tester(db)

        _auto_fund_tester_if_enabled(db, user)
        _auto_fund_tester_if_enabled(db, user)  # terms再同意を模した2回目呼び出し

        assert db.query(FundAllocation).count() == 1

    def test_disabled_in_production_even_if_configured(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=production なら金額設定済みでも常に無効。"""
        monkeypatch.setenv("AUTO_FUND_PARTNER_ID", "9")
        monkeypatch.setenv("AUTO_FUND_TESTER_ALLOCATION_USD", "150000")
        monkeypatch.setenv("APP_ENV", "production")
        user = _make_tester(db)

        _auto_fund_tester_if_enabled(db, user)

        assert db.query(FundAllocation).count() == 0
