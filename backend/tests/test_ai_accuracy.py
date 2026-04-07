# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_accuracy.py
"""AI的中率計算ロジックのテスト。"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-accuracy")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "accuracy_admin@example.com")

from app.ai.accuracy import calculate_accuracy  # noqa: E402
from app.ai.models import AIDecision  # noqa: E402
from app.database import Base  # noqa: E402


@pytest.fixture()
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _add_decision(db: Session, action: str, agreed: bool, days_ago: int = 0) -> AIDecision:
    d = AIDecision(
        query="test",
        action=action,
        confidence=70,
        primary_provider="claude",
        primary_action=action,
        primary_confidence=70,
        agreed=agreed,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(d)
    db.commit()
    return d


class TestCalculateAccuracy:
    def test_empty_db_returns_zeros(self, db):
        result = calculate_accuracy(db)
        assert result.total_decisions == 0
        assert result.correct_count == 0
        assert result.accuracy_pct == Decimal("0.00")
        assert result.last_30d_accuracy_pct == Decimal("0.00")
        assert result.by_action["BUY"].total == 0
        assert result.by_action["SELL"].total == 0

    def test_hold_excluded(self, db):
        _add_decision(db, "HOLD", agreed=True)
        _add_decision(db, "HOLD", agreed=False)
        result = calculate_accuracy(db)
        assert result.total_decisions == 0

    def test_buy_correct(self, db):
        _add_decision(db, "BUY", agreed=True)
        _add_decision(db, "BUY", agreed=False)
        result = calculate_accuracy(db)
        assert result.total_decisions == 2
        assert result.correct_count == 1
        assert result.accuracy_pct == Decimal("50.00")
        assert result.by_action["BUY"].total == 2
        assert result.by_action["BUY"].correct == 1
        assert result.by_action["BUY"].pct == Decimal("50.00")

    def test_sell_correct(self, db):
        _add_decision(db, "SELL", agreed=True)
        result = calculate_accuracy(db)
        assert result.total_decisions == 1
        assert result.correct_count == 1
        assert result.accuracy_pct == Decimal("100.00")
        assert result.by_action["SELL"].pct == Decimal("100.00")

    def test_mixed_buy_sell(self, db):
        _add_decision(db, "BUY", agreed=True)
        _add_decision(db, "BUY", agreed=True)
        _add_decision(db, "SELL", agreed=False)
        _add_decision(db, "HOLD", agreed=True)  # excluded
        result = calculate_accuracy(db)
        assert result.total_decisions == 3
        assert result.correct_count == 2
        assert result.accuracy_pct == Decimal("66.67")

    def test_days_filter(self, db):
        _add_decision(db, "BUY", agreed=True, days_ago=5)
        _add_decision(db, "BUY", agreed=False, days_ago=40)  # outside 30d
        result = calculate_accuracy(db, days=30)
        assert result.total_decisions == 1
        assert result.correct_count == 1

    def test_last_30d_accuracy_independent_of_days_param(self, db):
        _add_decision(db, "BUY", agreed=True, days_ago=5)
        _add_decision(db, "SELL", agreed=False, days_ago=60)  # outside 30d
        result = calculate_accuracy(db)
        # total includes both, last_30d only includes the recent one
        assert result.total_decisions == 2
        assert result.last_30d_accuracy_pct == Decimal("100.00")

    def test_accuracy_pct_precision(self, db):
        # 1/3 ≈ 33.33%
        _add_decision(db, "BUY", agreed=True)
        _add_decision(db, "BUY", agreed=False)
        _add_decision(db, "BUY", agreed=False)
        result = calculate_accuracy(db)
        assert result.accuracy_pct == Decimal("33.33")

    def test_all_incorrect(self, db):
        _add_decision(db, "BUY", agreed=False)
        _add_decision(db, "SELL", agreed=False)
        result = calculate_accuracy(db)
        assert result.accuracy_pct == Decimal("0.00")
        assert result.correct_count == 0
